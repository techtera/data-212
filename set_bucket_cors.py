"""Set CORS on the GCS bucket to allow direct uploads from localhost.

Run once:
    cd D:\\TERAFAC\\AGENTIC-UI\\backend
    .\\venv\\Scripts\\Activate.ps1
    python set_bucket_cors.py
"""

from pathlib import Path

from google.cloud import storage

# Load SA credentials (same path as the backend uses)
SA_KEY = "gcs-service-account.json"
BUCKET_NAME = "terafac-datasets"

CORS_CONFIG = [
    {
        "origin": ["*"],
        "method": ["PUT", "GET", "OPTIONS"],
        "responseHeader": ["Content-Type", "Content-Length"],
        "maxAgeSeconds": 3600,
    }
]


def main():
    if not Path(SA_KEY).exists():
        print(f"ERROR: {SA_KEY} not found. Run from backend/ directory.")
        return

    client = storage.Client.from_service_account_json(SA_KEY)
    bucket = client.bucket(BUCKET_NAME)

    # Don't reload (requires storage.buckets.get) — just set CORS directly
    bucket.cors = CORS_CONFIG
    try:
        bucket.patch()
        print(f"CORS configured on {BUCKET_NAME}!")
        print(f"Origins: {[c['origin'] for c in CORS_CONFIG]}")
    except Exception as e:
        print(f"ERROR: {e}")
        print()
        print("The SA likely needs 'roles/storage.legacyBucketOwner' or")
        print("'roles/storage.admin' to set CORS. Ask the project owner to")
        print("either grant the permission or run this manually:")
        print()
        print(f'  gsutil cors set gcs-cors.json gs://{BUCKET_NAME}')
        print()
        print("Or set CORS from the GCP Console -> Storage -> Bucket -> Permissions")


if __name__ == "__main__":
    main()
