"""Training service - SSH-based or stub mode for running eval/finetune on GCP VM."""

import asyncio
import json
import logging
import random

from .config import settings
from .db import execute, fetch_one
from .models import get_model_by_name

logger = logging.getLogger(__name__)

VM_WORKDIR = "/home/terafacdata_gmail_com/Shubhojit"
VM_VENV = f"{VM_WORKDIR}/venv/bin/python"


async def run_eval(job_id: str, model_name: str, job_name: str) -> None:
    """Run model evaluation. Dispatches to stub or SSH based on TRAINING_MODE."""
    try:
        if settings.TRAINING_MODE == "stub":
            await _stub_eval(job_id, model_name, job_name)
        else:
            await _ssh_eval(job_id, model_name, job_name)
    except Exception as e:
        logger.exception("Eval job %s failed", job_id)
        await execute(
            "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
            str(e),
            job_id,
        )


async def run_finetune(job_id: str, model_name: str, job_name: str) -> None:
    """Run model fine-tuning. Dispatches to stub or SSH based on TRAINING_MODE."""
    try:
        if settings.TRAINING_MODE == "stub":
            await _stub_finetune(job_id, model_name, job_name)
        else:
            await _ssh_finetune(job_id, model_name, job_name)
    except Exception as e:
        logger.exception("Finetune job %s failed", job_id)
        await execute(
            "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
            str(e),
            job_id,
        )


# ---------------------------------------------------------------------------
# Stub mode (local development)
# ---------------------------------------------------------------------------


async def _stub_eval(job_id: str, model_name: str, job_name: str) -> None:
    """Fake eval for local dev. Waits 5s then sets dummy metrics."""
    await asyncio.sleep(5)
    await execute(
        """UPDATE jobs
           SET status = 'done',
               mean_iou = $1,
               dice_score = $2,
               pixel_accuracy = $3,
               updated_at = NOW()
           WHERE id = $4""",
        round(random.uniform(0.6, 0.95), 4),
        round(random.uniform(0.7, 0.98), 4),
        round(random.uniform(0.8, 0.99), 4),
        job_id,
    )


async def _stub_finetune(job_id: str, model_name: str, job_name: str) -> None:
    """Fake finetune for local dev."""
    await asyncio.sleep(10)
    await execute(
        """UPDATE jobs
           SET status = 'done',
               artifacts = $1::jsonb,
               updated_at = NOW()
           WHERE id = $2""",
        json.dumps({
            "checkpoint": f"finetune/{job_name}/{model_name}/best.pt",
            "inference_script": f"finetune/{job_name}/{model_name}/run_inference.py",
        }),
        job_id,
    )


# ---------------------------------------------------------------------------
# SSH mode (real GCP VM)
# ---------------------------------------------------------------------------


def _get_ssh_client():
    """Create a paramiko SSH client connected to the training VM."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_path = settings.VM_SSH_KEY_PATH
    pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
    client.connect(
        hostname=settings.VM_HOST,
        username=settings.VM_USER,
        pkey=pkey,
        timeout=30,
    )
    return client


def _ssh_exec(client, command: str) -> str:
    """Execute a command over SSH and return stdout."""
    _, stdout, stderr = client.exec_command(command, timeout=120)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()

    if exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {err[:500]}")

    return out


async def _ssh_eval(job_id: str, model_name: str, job_name: str) -> None:
    """Run evaluation on the GCP VM via SSH inside a screen session."""
    model_info = get_model_by_name(model_name)
    if not model_info:
        raise RuntimeError(f"Model not found: {model_name}")

    # Parse model weights path (gs://bucket/blob)
    load_path = model_info["load_path"]
    model_parts = load_path.replace("gs://", "").split("/", 1)
    model_bucket = model_parts[0]
    model_blob = model_parts[1]
    model_filename = model_blob.split("/")[-1]

    # Parse inference script path (gs://bucket/blob)
    script_path = model_info["inference_script"]
    script_parts = script_path.replace("gs://", "").split("/", 1)
    script_bucket = script_parts[0]
    script_blob = script_parts[1]
    script_filename = script_blob.split("/")[-1]

    images_gcs_path = f"upload/{job_name}/images.zip"
    data_bucket = settings.GCS_BUCKET_NAME

    client = _get_ssh_client()
    job_dir = f"{VM_WORKDIR}/jobs/{job_id}"
    screen_name = f"job_{job_id[:8]}"

    try:
        _ssh_exec(client, f"mkdir -p {job_dir}/logs")

        job_script = f"""#!/bin/bash
VENV="{VM_VENV}"
JOB_DIR="{job_dir}"
LOG="{job_dir}/logs/run.log"

# Trap errors — write ERROR status so poller doesn't loop forever
trap 'echo "SCRIPT FAILED at line $LINENO" >> "$LOG"; echo "ERROR" > "$JOB_DIR/status"; exit 1' ERR

set -e
exec > >(tee -a "$LOG") 2>&1
echo "=== Job {job_id} started at $(date) ==="
echo "Model: {model_name} | Job: {job_name}"

# 1. Download inference script from GCS
echo "Downloading inference script from GCS..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{script_bucket}')
b.blob('{script_blob}').download_to_filename('$JOB_DIR/{script_filename}')
print('Inference script downloaded: {script_filename}')
"

# 2. Download model
echo "Downloading model..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{model_bucket}')
b.blob('{model_blob}').download_to_filename('$JOB_DIR/{model_filename}')
print('Model downloaded: {model_filename}')
"

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

# 4. Extract images (filter out mask/ground-truth files)
cd "$JOB_DIR"
unzip -o -q images.zip -d images_raw
mv images_raw/images/* images/ 2>/dev/null || mv images_raw/* images/ 2>/dev/null
rm -rf images_raw images.zip
find "$JOB_DIR/images" -type f \( -name "*_mask*" -o -name "*mask_*" -o -name "*_gt*" \) -delete

# 5. Run inference (unified CLI format)
echo "Running inference..."
$VENV "$JOB_DIR/{script_filename}" \\
    --model-path "$JOB_DIR/{model_filename}" \\
    --images-dir "$JOB_DIR/images" \\
    --output-dir "$JOB_DIR/output" \\
    --job-id {job_id}

# 6. Upload predictions to GCS at inference/jobname/
echo "Uploading predictions..."
$VENV -c "
import os
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
pred_dir = '$JOB_DIR/output/predictions'
files = os.listdir(pred_dir) if os.path.isdir(pred_dir) else []
for f in files:
    b.blob(f'inference/{job_name}/predictions/{{f}}').upload_from_filename(f'{{pred_dir}}/{{f}}')
print(f'Uploaded {{len(files)}} predictions to GCS')
"

# 7. Upload metrics.json to GCS (if exists)
if [ -f "$JOB_DIR/output/metrics.json" ]; then
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('inference/{job_name}/metrics.json').upload_from_filename('$JOB_DIR/output/metrics.json')
print('Metrics uploaded to GCS')
"
cp "$JOB_DIR/output/metrics.json" "$JOB_DIR/results.json"
else
echo '{{"mean_iou": 0, "dice_score": 0, "pixel_accuracy": 0, "predictions": []}}' > "$JOB_DIR/results.json"
fi

# 8. Mark done
echo "DONE" > "$JOB_DIR/status"

echo "=== Job {job_id} finished at $(date) ==="
"""

        _ssh_exec(client, f"cat > {job_dir}/run_job.sh << 'JOBEOF'\n{job_script}\nJOBEOF")
        _ssh_exec(client, f"chmod +x {job_dir}/run_job.sh")

        _ssh_exec(client, f"screen -dmS {screen_name} bash {job_dir}/run_job.sh")
        logger.info("Job %s launched in screen '%s'", job_id, screen_name)

    finally:
        client.close()

    await _poll_vm_job(job_id, job_dir, data_bucket, job_name)


async def _poll_vm_job(job_id: str, job_dir: str, bucket: str, job_name: str) -> None:
    """Poll the VM for job completion by checking the status file."""
    poll_interval = 10
    max_polls = 360  # 60 minutes max

    for i in range(max_polls):
        await asyncio.sleep(poll_interval)

        try:
            client = _get_ssh_client()
            try:
                status = _ssh_exec(client, f"cat {job_dir}/status 2>/dev/null || echo RUNNING").strip()

                if status == "ERROR":
                    error_log = _ssh_exec(client, f"tail -20 {job_dir}/logs/run.log 2>/dev/null || echo 'Unknown error'").strip()
                    last_lines = error_log.split("\n")[-5:]
                    error_msg = "\n".join(last_lines)
                    await execute(
                        "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
                        error_msg[:500],
                        job_id,
                    )
                    _ssh_exec(client, f"rm -rf {job_dir}")
                    logger.error("Job %s failed on VM: %s", job_id, error_msg[:200])
                    return

                if status == "DONE":
                    # Read results.json (may have metrics and/or predictions list)
                    results_raw = _ssh_exec(client, f"cat {job_dir}/results.json 2>/dev/null || echo '{{}}'")
                    results = json.loads(results_raw)

                    # Get predictions: from results.json or by listing the output dir
                    preds_from_json = results.get("predictions", [])
                    if preds_from_json:
                        gcs_predictions = [
                            f"inference/{job_name}/predictions/{p.split('/')[-1]}"
                            for p in preds_from_json
                        ]
                    else:
                        # List prediction files directly from VM output dir
                        pred_list = _ssh_exec(client, f"ls {job_dir}/output/predictions/ 2>/dev/null || echo ''").strip()
                        pred_files = [f for f in pred_list.split("\n") if f.strip()]
                        gcs_predictions = [
                            f"inference/{job_name}/predictions/{f}"
                            for f in pred_files
                        ]

                    await execute(
                        """UPDATE jobs
                           SET status = 'done',
                               mean_iou = $1,
                               dice_score = $2,
                               pixel_accuracy = $3,
                               predictions = $4::jsonb,
                               updated_at = NOW()
                           WHERE id = $5""",
                        results.get("mean_iou", 0),
                        results.get("dice_score", 0),
                        results.get("pixel_accuracy", 0),
                        json.dumps(gcs_predictions),
                        job_id,
                    )
                    _ssh_exec(client, f"rm -rf {job_dir}")
                    logger.info("Job %s completed successfully, VM cleaned", job_id)
                    return

            finally:
                client.close()

        except Exception as e:
            logger.warning("Poll %d for job %s failed: %s", i, job_id, e)

    await execute(
        "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
        "Job timed out after 60 minutes",
        job_id,
    )


async def _ssh_finetune(job_id: str, model_name: str, job_name: str) -> None:
    """Fine-tuning on VM. Currently returns error - not yet enabled."""
    await execute(
        "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
        "Fine-tuning is not yet enabled. Only pretrained inference is available.",
        job_id,
    )
