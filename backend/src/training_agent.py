"""Agent training on VM — separate pipeline from normal training.py."""

import asyncio
import json
import logging
from uuid import UUID

from .config import settings
from .db import execute, fetch_one, fetch_all
from .models import get_model_by_name_async

logger = logging.getLogger(__name__)

VM_WORKDIR = "/home/terafacdata_gmail_com/Shubhojit"
VM_VENV = f"{VM_WORKDIR}/venv/bin/python"

MAX_AUTO_RETRIES = 10


def _get_ssh_client():
    """Create SSH client — same as training.py but kept here for independence."""
    import io
    import os
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_value = settings.VM_SSH_KEY_PATH
    if r"\n" in key_value:
        key_value = key_value.replace(r"\n", "\n")

    if "PRIVATE KEY" in key_value:
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(key_value))
    elif os.path.isfile(key_value):
        pkey = paramiko.Ed25519Key.from_private_key_file(key_value)
    else:
        pem = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + key_value.strip() + "\n-----END OPENSSH PRIVATE KEY-----\n"
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))

    client.connect(hostname=settings.VM_HOST, username=settings.VM_USER, pkey=pkey, timeout=30)
    return client


def _ssh_exec(client, command: str) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=120)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {err[:500]}")
    return out


# ---------------------------------------------------------------------------
# Agent Training
# ---------------------------------------------------------------------------


async def run_agent_train(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """Run agent-generated training. Separate from normal finetune pipeline."""
    try:
        await _launch_agent_train(job_id, model_name, job_name, owner_id)
        await _poll_agent_job(job_id, f"{VM_WORKDIR}/jobs/{job_id}", settings.GCS_BUCKET_NAME, job_name, model_name, owner_id)
    except Exception as e:
        logger.exception("Agent train job %s failed", job_id)
        await execute(
            "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
            str(e)[:500], job_id,
        )


async def _launch_agent_train(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """SSH to VM: clean dir, download code+data fresh, launch training in screen."""
    model_info = await get_model_by_name_async(model_name, owner_id)
    if not model_info:
        raise RuntimeError(f"Model not found: {model_name}")

    script_gs = model_info.get("finetune_script", "") or model_info.get("inference_script", "")
    if not script_gs:
        raise RuntimeError(f"No training script for agent model: {model_name}")

    script_parts = script_gs.replace("gs://", "").split("/", 1)
    script_bucket = script_parts[0]
    script_blob = script_parts[1]

    images_gcs_path = f"upload/{owner_id}/{job_name}/images.zip"
    masks_gcs_path = f"upload/{owner_id}/{job_name}/masks.zip"
    data_bucket = settings.GCS_BUCKET_NAME

    # Read epochs/lr from job artifacts
    job_record = await fetch_one("SELECT artifacts FROM jobs WHERE id = $1", job_id)
    training_config = {}
    if job_record and job_record["artifacts"]:
        arts = job_record["artifacts"] if isinstance(job_record["artifacts"], dict) else json.loads(job_record["artifacts"] or "{}")
        training_config = {k: v for k, v in arts.items() if k in ("epochs", "lr")}
    epochs = training_config.get("epochs", 10)
    lr = training_config.get("lr", 0.0001)

    client = _get_ssh_client()
    job_dir = f"{VM_WORKDIR}/jobs/{job_id}"
    screen_name = f"ag_{job_id[:8]}"

    try:
        _ssh_exec(client, f"rm -rf {job_dir} && mkdir -p {job_dir}/logs")

        job_script = f"""#!/bin/bash
VENV="{VM_VENV}"
JOB_DIR="{job_dir}"
LOG="{job_dir}/logs/run.log"

trap 'echo "SCRIPT FAILED at line $LINENO" >> "$LOG"; echo "ERROR" > "$JOB_DIR/status"; exit 1' ERR

set -e
exec > >(tee -a "$LOG") 2>&1
echo "=== Agent Train Job {job_id} ==="

# 1. Download training script
echo "Downloading training script..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{script_bucket}')
b.blob('{script_blob}').download_to_filename('$JOB_DIR/train.py')
print('Script downloaded')
"

# 2. Download images and masks
echo "Downloading data..."
mkdir -p "$JOB_DIR/images" "$JOB_DIR/masks" "$JOB_DIR/output/predictions"
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('{images_gcs_path}').download_to_filename('$JOB_DIR/images.zip')
b.blob('{masks_gcs_path}').download_to_filename('$JOB_DIR/masks.zip')
print('Data downloaded')
"

# 3. Extract and flatten
cd "$JOB_DIR"
unzip -o -q images.zip -d images_raw
find images_raw -type f \\( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \\) -exec mv {{}} images/ \\;
rm -rf images_raw images.zip

unzip -o -q masks.zip -d masks_raw
find masks_raw -type f \\( -name "*.png" -o -name "*.jpg" -o -name "*.txt" -o -name "*.jpeg" \\) -exec mv {{}} masks/ \\;
rm -rf masks_raw masks.zip

echo "Images: $(ls images/ | wc -l), Masks: $(ls masks/ | wc -l)"

# 4. Run training
echo "Running training..."
$VENV "$JOB_DIR/train.py" \\
    --model-path "" \\
    --images-dir "$JOB_DIR/images" \\
    --masks-dir "$JOB_DIR/masks" \\
    --output-dir "$JOB_DIR/output" \\
    --job-id {job_id} \\
    --split 0.9 \\
    --epochs {epochs} \\
    --lr {lr}

# 5. Upload results
echo "Uploading results..."
$VENV -c "
import os
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
if os.path.exists('$JOB_DIR/output/best.pt'):
    b.blob('finetune/{owner_id}/{job_name}/{model_name}/best.pt').upload_from_filename('$JOB_DIR/output/best.pt')
    print('Checkpoint uploaded')
pred_dir = '$JOB_DIR/output/predictions'
if os.path.isdir(pred_dir):
    for f in os.listdir(pred_dir):
        b.blob(f'finetune/{owner_id}/{job_name}/{model_name}/predictions/{{f}}').upload_from_filename(f'{{pred_dir}}/{{f}}')
    print(f'Uploaded {{len(os.listdir(pred_dir))}} predictions')
if os.path.exists('$JOB_DIR/output/metrics.json'):
    b.blob('finetune/{owner_id}/{job_name}/{model_name}/metrics.json').upload_from_filename('$JOB_DIR/output/metrics.json')
    print('Metrics uploaded')
"

# 6. Copy metrics for poller
cp "$JOB_DIR/output/metrics.json" "$JOB_DIR/results.json" 2>/dev/null || echo '{{}}' > "$JOB_DIR/results.json"

echo "DONE" > "$JOB_DIR/status"
echo "=== Agent Train Complete ==="
"""

        _ssh_exec(client, f"cat > {job_dir}/run_job.sh << 'JOBEOF'\n{job_script}\nJOBEOF")
        _ssh_exec(client, f"chmod +x {job_dir}/run_job.sh")
        _ssh_exec(client, f"screen -dmS {screen_name} bash {job_dir}/run_job.sh")
        logger.info("Agent train job %s launched (epochs=%s, lr=%s)", job_id, epochs, lr)

    finally:
        client.close()


async def _poll_agent_job(job_id: str, job_dir: str, bucket: str, job_name: str, model_name: str, owner_id: str = "") -> None:
    """Poll VM for agent training completion. Auto-retries up to MAX_AUTO_RETRIES times."""
    poll_interval = 15
    retry_count = 0

    while True:
        await asyncio.sleep(poll_interval)
        try:
            client = _get_ssh_client()
            try:
                status = _ssh_exec(client, f"cat {job_dir}/status 2>/dev/null || echo RUNNING").strip()

                if status == "ERROR":
                    error_log = _ssh_exec(client, f"tail -20 {job_dir}/logs/run.log 2>/dev/null || echo 'Unknown error'").strip()
                    last_lines = "\n".join(error_log.split("\n")[-5:])
                    _ssh_exec(client, f"rm -rf {job_dir}")
                    client.close()

                    if retry_count < MAX_AUTO_RETRIES:
                        retry_count += 1
                        logger.info("Agent train job %s failed (attempt %d/%d), auto-debugging...", job_id, retry_count, MAX_AUTO_RETRIES)
                        await execute(
                            "UPDATE jobs SET error_message = $1, updated_at = NOW() WHERE id = $2",
                            f"Auto-retry {retry_count}/{MAX_AUTO_RETRIES}: {last_lines[:200]}", job_id,
                        )
                        from .coding_training import auto_debug_train
                        fixed = await auto_debug_train(model_name, owner_id, last_lines)
                        if fixed:
                            await _launch_agent_train(job_id, model_name, job_name, owner_id)
                            continue

                    await execute(
                        "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
                        f"Failed after {retry_count} retries. Last error: {last_lines[:300]}", job_id,
                    )
                    return

                if status == "DONE":
                    results_raw = _ssh_exec(client, f"cat {job_dir}/results.json 2>/dev/null || echo '{{}}'")
                    results = json.loads(results_raw)

                    preds = results.get("predictions", [])
                    gcs_predictions = [f"finetune/{owner_id}/{job_name}/{model_name}/predictions/{p.split('/')[-1]}" for p in preds]

                    model_info_for_script = await get_model_by_name_async(model_name, owner_id)
                    train_script_blob = ""
                    if model_info_for_script:
                        ts = model_info_for_script.get("finetune_script", "") or model_info_for_script.get("training_script", "")
                        if ts:
                            train_script_blob = ts.replace(f"gs://{bucket}/", "")

                    artifacts = {
                        "checkpoint": f"finetune/{owner_id}/{job_name}/{model_name}/best.pt",
                        "inference_script": train_script_blob,
                        "epochs_trained": results.get("epochs_trained", 0),
                        "train_samples": results.get("train_samples", 0),
                        "val_samples": results.get("val_samples", 0),
                        "loss_type": results.get("loss_type", ""),
                        "train_metrics": results.get("train_metrics", {}),
                        "val_metrics": results.get("val_metrics", {}),
                        "epoch_history": results.get("epoch_history", []),
                    }

                    await execute(
                        """UPDATE jobs SET status = 'done', mean_iou = $1, dice_score = $2, pixel_accuracy = $3,
                           predictions = $4::jsonb, artifacts = $5::jsonb, updated_at = NOW() WHERE id = $6""",
                        results.get("mean_iou", 0), results.get("dice_score", 0), results.get("pixel_accuracy", 0),
                        json.dumps(gcs_predictions), json.dumps(artifacts), job_id,
                    )

                    checkpoint_gcs = f"finetune/{owner_id}/{job_name}/{model_name}/best.pt"
                    await execute(
                        "UPDATE user_models SET checkpoint_path = $1 WHERE model_name = $2 AND user_id = $3",
                        checkpoint_gcs, model_name, UUID(owner_id),
                    )

                    _ssh_exec(client, f"rm -rf {job_dir}")
                    logger.info("Agent train job %s completed", job_id)
                    return

            finally:
                client.close()

        except Exception as e:
            logger.warning("Poll for agent train job %s failed: %s", job_id, e)
