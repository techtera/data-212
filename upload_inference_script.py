"""Upload the fixed dino_model_inference.py to GCS.

Run:
    cd D:\\TERAFAC\\AGENTIC-UI\\backend
    .\\venv\\Scripts\\python upload_inference_script.py
"""

from pathlib import Path

from google.cloud import storage

SA_KEY = "gcs-service-account.json"
BUCKET_NAME = "terafac-datasets"

SCRIPTS = [
    {
        "local": Path(__file__).resolve().parent.parent / "model" / "code" / "dino_model_inference.py",
        "gcs_blob": "inference/code/unet_inference.py",
    },
    {
        "local": Path(__file__).resolve().parent.parent / "model" / "code" / "inference_standalone_obj.py",
        "gcs_blob": "inference/code/vggt_segformer_inference.py",
    },
    {
        "local": Path(__file__).resolve().parent.parent / "model" / "code" / "inference_standalone_edge.py",
        "gcs_blob": "inference/code/vggt_unetpp_inference.py",
    },
]


def main():
    if not Path(SA_KEY).exists():
        print(f"ERROR: {SA_KEY} not found. Run from backend/ directory.")
        return

    client = storage.Client.from_service_account_json(SA_KEY)
    bucket = client.bucket(BUCKET_NAME)

    for s in SCRIPTS:
        local_path = s["local"]
        blob_name = s["gcs_blob"]

        if not local_path.exists():
            print(f"SKIP: {local_path} not found")
            continue

        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path))
        print(f"Uploaded: {local_path.name} -> gs://{BUCKET_NAME}/{blob_name}")


if __name__ == "__main__":
    main()
