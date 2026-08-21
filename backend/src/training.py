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


async def run_eval(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """Run model evaluation. Dispatches to stub or SSH based on TRAINING_MODE."""
    try:
        if settings.TRAINING_MODE == "stub":
            await _stub_eval(job_id, model_name, job_name)
        else:
            await _ssh_eval(job_id, model_name, job_name, owner_id)
    except Exception as e:
        logger.exception("Eval job %s failed", job_id)
        await execute(
            "UPDATE jobs SET status = 'error', error_message = $1, updated_at = NOW() WHERE id = $2",
            str(e),
            job_id,
        )


async def run_finetune(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """Run model fine-tuning. Dispatches to stub or SSH based on TRAINING_MODE."""
    try:
        if settings.TRAINING_MODE == "stub":
            await _stub_finetune(job_id, model_name, job_name)
        else:
            await _ssh_finetune(job_id, model_name, job_name, owner_id)
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
            "checkpoint": f"finetune/stub/{job_name}/{model_name}/best.pt",
            "inference_script": f"finetune/stub/{job_name}/{model_name}/run_inference.py",
        }),
        job_id,
    )


# ---------------------------------------------------------------------------
# SSH mode (real GCP VM)
# ---------------------------------------------------------------------------


def _get_ssh_client():
    """Create a paramiko SSH client connected to the training VM."""
    import io
    import os
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_value = settings.VM_SSH_KEY_PATH
    if "PRIVATE KEY" in key_value:
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(key_value))
    elif key_value.startswith("b3Blbn") or key_value.startswith("AAAA"):
        pem = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + key_value.strip() + "\n-----END OPENSSH PRIVATE KEY-----\n"
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
    elif os.path.isfile(key_value):
        pkey = paramiko.Ed25519Key.from_private_key_file(key_value)
    else:
        pem = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + key_value.strip() + "\n-----END OPENSSH PRIVATE KEY-----\n"
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
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


async def _ssh_eval(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
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

    images_gcs_path = f"upload/{owner_id}/{job_name}/images.zip"
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
    b.blob(f'inference/{owner_id}/{job_name}/predictions/{{f}}').upload_from_filename(f'{{pred_dir}}/{{f}}')
print(f'Uploaded {{len(files)}} predictions to GCS')
"

# 7. Upload metrics.json to GCS (if exists)
if [ -f "$JOB_DIR/output/metrics.json" ]; then
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('inference/{owner_id}/{job_name}/metrics.json').upload_from_filename('$JOB_DIR/output/metrics.json')
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

    await _poll_vm_job(job_id, job_dir, data_bucket, job_name, owner_id)


async def _poll_vm_job(job_id: str, job_dir: str, bucket: str, job_name: str, owner_id: str = "") -> None:
    """Poll the VM for job completion by checking the status file."""
    poll_interval = 10
    while True:
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
                            f"inference/{owner_id}/{job_name}/predictions/{p.split('/')[-1]}"
                            for p in preds_from_json
                        ]
                    else:
                        # List prediction files directly from VM output dir
                        pred_list = _ssh_exec(client, f"ls {job_dir}/output/predictions/ 2>/dev/null || echo ''").strip()
                        pred_files = [f for f in pred_list.split("\n") if f.strip()]
                        gcs_predictions = [
                            f"inference/{owner_id}/{job_name}/predictions/{f}"
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



async def _ssh_finetune(job_id: str, model_name: str, job_name: str, owner_id: str = "") -> None:
    """Run fine-tuning on the GCP VM via SSH inside a screen session."""
    model_info = get_model_by_name(model_name)
    if not model_info:
        raise RuntimeError(f"Model not found: {model_name}")

    finetune_script_path = model_info.get("finetune_script", "")
    if not finetune_script_path:
        raise RuntimeError(f"No finetune script configured for model: {model_name}")

    load_path = model_info["load_path"]
    model_parts = load_path.replace("gs://", "").split("/", 1)
    model_bucket = model_parts[0]
    model_blob = model_parts[1]
    model_filename = model_blob.split("/")[-1]

    script_parts = finetune_script_path.replace("gs://", "").split("/", 1)
    script_bucket = script_parts[0]
    script_blob = script_parts[1]
    script_filename = script_blob.split("/")[-1]

    images_gcs_path = f"upload/{owner_id}/{job_name}/images.zip"
    masks_gcs_path = f"upload/{owner_id}/{job_name}/masks.zip"
    data_bucket = settings.GCS_BUCKET_NAME

    # Read custom training config (epochs/lr) from job artifacts
    job_row = await fetch_one("SELECT artifacts FROM jobs WHERE id = $1", job_id)
    training_config = {}
    if job_row and job_row["artifacts"]:
        tc = job_row["artifacts"] if isinstance(job_row["artifacts"], dict) else json.loads(job_row["artifacts"] or "{}")
        training_config = tc

    extra_args = ""
    if training_config.get("epochs"):
        extra_args += f" --epochs {training_config['epochs']}"
    if training_config.get("lr"):
        extra_args += f" --lr {training_config['lr']}"

    client = _get_ssh_client()
    job_dir = f"{VM_WORKDIR}/jobs/{job_id}"
    screen_name = f"ft_{job_id[:8]}"

    try:
        _ssh_exec(client, f"mkdir -p {job_dir}/logs")

        job_script = f"""#!/bin/bash
VENV="{VM_VENV}"
JOB_DIR="{job_dir}"
LOG="{job_dir}/logs/run.log"

trap 'echo "SCRIPT FAILED at line $LINENO" >> "$LOG"; echo "ERROR" > "$JOB_DIR/status"; exit 1' ERR

set -e
exec > >(tee -a "$LOG") 2>&1
echo "=== Finetune Job {job_id} started at $(date) ==="
echo "Model: {model_name} | Job: {job_name}"

# 1. Download finetune script
echo "Downloading finetune script..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{script_bucket}')
b.blob('{script_blob}').download_to_filename('$JOB_DIR/{script_filename}')
print('Finetune script downloaded: {script_filename}')
"

# 2. Download pretrained model
echo "Downloading pretrained model..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{model_bucket}')
b.blob('{model_blob}').download_to_filename('$JOB_DIR/{model_filename}')
print('Model downloaded: {model_filename}')
"

# 3. Download images and masks
echo "Downloading images and masks..."
mkdir -p "$JOB_DIR/images" "$JOB_DIR/masks" "$JOB_DIR/output/predictions"
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('{images_gcs_path}').download_to_filename('$JOB_DIR/images.zip')
b.blob('{masks_gcs_path}').download_to_filename('$JOB_DIR/masks.zip')
print('Images and masks downloaded')
"

# 4. Extract images and masks
cd "$JOB_DIR"
unzip -o -q images.zip -d images_raw
mv images_raw/images/* images/ 2>/dev/null || mv images_raw/* images/ 2>/dev/null
rm -rf images_raw images.zip

unzip -o -q masks.zip -d masks_raw
mv masks_raw/masks/* masks/ 2>/dev/null || mv masks_raw/* masks/ 2>/dev/null
rm -rf masks_raw masks.zip

# 5. Run finetune
echo "Running fine-tuning..."
$VENV "$JOB_DIR/{script_filename}" \\
    --model-path "$JOB_DIR/{model_filename}" \\
    --images-dir "$JOB_DIR/images" \\
    --masks-dir "$JOB_DIR/masks" \\
    --output-dir "$JOB_DIR/output" \\
    --job-id {job_id} \\
    --split 0.9{extra_args}

# 6. Upload checkpoint to GCS
echo "Uploading checkpoint..."
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('finetune/{owner_id}/{job_name}/{model_name}/best.pt').upload_from_filename('$JOB_DIR/output/best.pt')
print('Checkpoint uploaded')
"

# 7. Upload predictions to GCS
echo "Uploading val predictions..."
$VENV -c "
import os
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
pred_dir = '$JOB_DIR/output/predictions'
files = os.listdir(pred_dir) if os.path.isdir(pred_dir) else []
for f in files:
    b.blob(f'finetune/{owner_id}/{job_name}/{model_name}/predictions/{{f}}').upload_from_filename(f'{{pred_dir}}/{{f}}')
print(f'Uploaded {{len(files)}} val predictions to GCS')
"

# 8. Upload metrics.json to GCS
if [ -f "$JOB_DIR/output/metrics.json" ]; then
$VENV -c "
from google.cloud import storage
c = storage.Client()
b = c.bucket('{data_bucket}')
b.blob('finetune/{owner_id}/{job_name}/{model_name}/metrics.json').upload_from_filename('$JOB_DIR/output/metrics.json')
print('Metrics uploaded to GCS')
"
cp "$JOB_DIR/output/metrics.json" "$JOB_DIR/results.json"
else
echo '{{"mean_iou": 0, "dice_score": 0, "pixel_accuracy": 0, "predictions": []}}' > "$JOB_DIR/results.json"
fi

# 9. Mark done
echo "DONE" > "$JOB_DIR/status"
echo "=== Finetune Job {job_id} finished at $(date) ==="
"""

        _ssh_exec(client, f"cat > {job_dir}/run_job.sh << 'JOBEOF'\n{job_script}\nJOBEOF")
        _ssh_exec(client, f"chmod +x {job_dir}/run_job.sh")

        _ssh_exec(client, f"screen -dmS {screen_name} bash {job_dir}/run_job.sh")
        logger.info("Finetune job %s launched in screen '%s'", job_id, screen_name)

    finally:
        client.close()

    await _poll_vm_finetune(job_id, job_dir, data_bucket, job_name, model_name, owner_id)


async def _poll_vm_finetune(job_id: str, job_dir: str, bucket: str, job_name: str, model_name: str, owner_id: str = "") -> None:
    """Poll the VM for finetune job completion."""
    poll_interval = 15
    while True:
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
                    logger.error("Finetune job %s failed: %s", job_id, error_msg[:200])
                    return

                if status == "DONE":
                    results_raw = _ssh_exec(client, f"cat {job_dir}/results.json 2>/dev/null || echo '{{}}'")
                    results = json.loads(results_raw)

                    preds_from_json = results.get("predictions", [])
                    gcs_predictions = [
                        f"finetune/{owner_id}/{job_name}/{model_name}/predictions/{p.split('/')[-1]}"
                        for p in preds_from_json
                    ]

                    if not gcs_predictions:
                        pred_list = _ssh_exec(client, f"ls {job_dir}/output/predictions/ 2>/dev/null || echo ''").strip()
                        pred_files = [f for f in pred_list.split("\n") if f.strip()]
                        gcs_predictions = [
                            f"finetune/{owner_id}/{job_name}/{model_name}/predictions/{f}"
                            for f in pred_files
                        ]

                    model_info = get_model_by_name(model_name)
                    inference_script_blob = ""
                    if model_info:
                        usr_script = model_info.get("usr_inference_script", "")
                        if usr_script:
                            inference_script_blob = usr_script.replace(f"gs://{bucket}/", "")

                    artifacts = {
                        "checkpoint": f"finetune/{owner_id}/{job_name}/{model_name}/best.pt",
                        "inference_script": inference_script_blob,
                        "metrics": f"finetune/{owner_id}/{job_name}/{model_name}/metrics.json",
                        "epochs_trained": results.get("epochs_trained", 0),
                        "best_epoch": results.get("best_epoch", 0),
                        "train_samples": results.get("train_samples", 0),
                        "val_samples": results.get("val_samples", 0),
                        "loss_type": results.get("loss_type", ""),
                        "train_metrics": results.get("train_metrics", {}),
                        "val_metrics": results.get("val_metrics", {}),
                        "epoch_history": results.get("epoch_history", []),
                    }

                    await execute(
                        """UPDATE jobs
                           SET status = 'done',
                               mean_iou = $1,
                               dice_score = $2,
                               pixel_accuracy = $3,
                               predictions = $4::jsonb,
                               artifacts = $5::jsonb,
                               updated_at = NOW()
                           WHERE id = $6""",
                        results.get("mean_iou", 0),
                        results.get("dice_score", 0),
                        results.get("pixel_accuracy", 0),
                        json.dumps(gcs_predictions),
                        json.dumps(artifacts),
                        job_id,
                    )
                    _ssh_exec(client, f"rm -rf {job_dir}")
                    logger.info("Finetune job %s completed, VM cleaned", job_id)
                    return

            finally:
                client.close()

        except Exception as e:
            logger.warning("Poll %d for finetune job %s failed: %s", i, job_id, e)

