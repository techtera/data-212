"""Agent inference on VM — separate from normal inference in training.py."""

import asyncio
import json
import logging

from .config import settings
from .db import execute, fetch_one
from .models import get_model_by_name_async

logger = logging.getLogger(__name__)

VM_WORKDIR = "/home/terafacdata_gmail_com/Shubhojit"
VM_VENV = f"{VM_WORKDIR}/venv/bin/python"

MAX_AUTO_RETRIES = 10


def _get_ssh_client():
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


async def run_agent_inference(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """Run agent-generated inference on VM."""
    try:
        await _launch_agent_inference(job_id, model_name, job_name, owner_id)
        await _poll_agent_inference(job_id, f"{VM_WORKDIR}/jobs/{job_id}", settings.GCS_BUCKET_NAME, job_name, model_name, owner_id)
    except Exception as e:
        logger.exception("Agent inference job %s failed", job_id)
        await execute(
            "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
            str(e)[:500], job_id,
        )


async def _launch_agent_inference(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """SSH to VM: clean dir, download inference script + checkpoint + images, launch in screen."""
    model_info = await get_model_by_name_async(model_name, owner_id)
    if not model_info:
        raise RuntimeError(f"Model not found: {model_name}")

    script_gs = model_info.get("inference_script", "") or model_info.get("usr_inference_script", "")
    if not script_gs:
        raise RuntimeError(f"No inference script for model: {model_name}")

    script_parts = script_gs.replace("gs://", "").split("/", 1)
    script_bucket = script_parts[0]
    script_blob = script_parts[1]

    load_path = model_info.get("load_path", "")
    has_checkpoint = bool(load_path and load_path.startswith("gs://"))
    if has_checkpoint:
        ckpt_parts = load_path.replace("gs://", "").split("/", 1)
        ckpt_bucket = ckpt_parts[0]
        ckpt_blob = ckpt_parts[1]
        ckpt_filename = ckpt_blob.split("/")[-1]
    else:
        ckpt_bucket = ckpt_blob = ckpt_filename = ""

    images_gcs_path = f"upload/{owner_id}/{job_name}/images.zip"
    data_bucket = settings.GCS_BUCKET_NAME

    client = _get_ssh_client()
    job_dir = f"{VM_WORKDIR}/jobs/{job_id}"
    screen_name = f"ai_{job_id[:8]}"

    try:
        _ssh_exec(client, f"rm -rf {job_dir} && mkdir -p {job_dir}/logs")

        job_script = f"""#!/bin/bash
VENV="{VM_VENV}"
JOB_DIR="{job_dir}"
LOG="{job_dir}/logs/run.log"

trap 'echo "SCRIPT FAILED at line $LINENO" >> "$LOG"; echo "ERROR" > "$JOB_DIR/status"; exit 1' ERR

set -e
exec > >(tee -a "$LOG") 2>&1
echo "=== Agent Inference Job {job_id} ==="

# 1. Download inference script
echo "Downloading inference script..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{script_bucket}')
b.blob('{script_blob}').download_to_filename('$JOB_DIR/script.py')
print('Script downloaded')
"

# 2. Download checkpoint
if [ -n "{ckpt_filename}" ]; then
echo "Downloading model checkpoint..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{ckpt_bucket}')
b.blob('{ckpt_blob}').download_to_filename('$JOB_DIR/{ckpt_filename}')
print('Checkpoint downloaded')
"
fi

# 3. Download images
echo "Downloading images..."
mkdir -p "$JOB_DIR/images" "$JOB_DIR/output/predictions"
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('{images_gcs_path}').download_to_filename('$JOB_DIR/images.zip')
print('Images downloaded')
"

# 4. Extract and flatten
cd "$JOB_DIR"
unzip -o -q images.zip -d images_raw
find images_raw -type f \\( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \\) -exec mv {{}} images/ \\;
rm -rf images_raw images.zip

echo "Images: $(ls images/ | wc -l)"

# 5. Run inference
echo "Running inference..."
$VENV "$JOB_DIR/script.py" \\
    --model-path "$JOB_DIR/{ckpt_filename}" \\
    --images-dir "$JOB_DIR/images" \\
    --output-dir "$JOB_DIR/output" \\
    --job-id {job_id}

# 6. Upload predictions
echo "Uploading predictions..."
$VENV -c "
import os
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
pred_dir = '$JOB_DIR/output/predictions'
if os.path.isdir(pred_dir):
    for f in os.listdir(pred_dir):
        b.blob(f'inference/{owner_id}/{job_name}/predictions/{{f}}').upload_from_filename(f'{{pred_dir}}/{{f}}')
    print(f'Uploaded {{len(os.listdir(pred_dir))}} predictions')
if os.path.exists('$JOB_DIR/output/metrics.json'):
    b.blob('inference/{owner_id}/{job_name}/metrics.json').upload_from_filename('$JOB_DIR/output/metrics.json')
    print('Metrics uploaded')
"

cp "$JOB_DIR/output/metrics.json" "$JOB_DIR/results.json" 2>/dev/null || echo '{{"predictions":[]}}' > "$JOB_DIR/results.json"

echo "DONE" > "$JOB_DIR/status"
echo "=== Agent Inference Complete ==="
"""

        _ssh_exec(client, f"cat > {job_dir}/run_job.sh << 'JOBEOF'\n{job_script}\nJOBEOF")
        _ssh_exec(client, f"chmod +x {job_dir}/run_job.sh")
        _ssh_exec(client, f"screen -dmS {screen_name} bash {job_dir}/run_job.sh")
        logger.info("Agent inference job %s launched", job_id)

    finally:
        client.close()


async def _poll_agent_inference(job_id: str, job_dir: str, bucket: str, job_name: str, model_name: str, owner_id: str = "") -> None:
    """Poll VM for agent inference completion. Auto-retries up to MAX_AUTO_RETRIES times."""
    poll_interval = 10
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
                        logger.info("Agent inference job %s failed (attempt %d/%d), auto-debugging...", job_id, retry_count, MAX_AUTO_RETRIES)
                        await execute(
                            "UPDATE jobs SET error_message = $1, updated_at = NOW() WHERE id = $2",
                            f"Auto-retry {retry_count}/{MAX_AUTO_RETRIES}: {last_lines[:200]}", job_id,
                        )
                        from .coding_inference import auto_debug_inference
                        fixed = await auto_debug_inference(model_name, owner_id, last_lines)
                        if fixed:
                            await _launch_agent_inference(job_id, model_name, job_name, owner_id)
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
                    gcs_predictions = [f"inference/{owner_id}/{job_name}/predictions/{p.split('/')[-1]}" for p in preds]
                    if not gcs_predictions:
                        pred_list = _ssh_exec(client, f"ls {job_dir}/output/predictions/ 2>/dev/null || echo ''").strip()
                        gcs_predictions = [f"inference/{owner_id}/{job_name}/predictions/{f}" for f in pred_list.split("\n") if f.strip()]

                    await execute(
                        """UPDATE jobs SET status = 'done', error_message = NULL, predictions = $1::jsonb, updated_at = NOW() WHERE id = $2""",
                        json.dumps(gcs_predictions), job_id,
                    )

                    _ssh_exec(client, f"rm -rf {job_dir}")
                    logger.info("Agent inference job %s completed", job_id)
                    return

            finally:
                client.close()

        except Exception as e:
            logger.warning("Poll for agent inference job %s failed: %s", job_id, e)
