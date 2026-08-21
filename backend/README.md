# TERAFAC Backend

FastAPI backend for the TERAFAC segmentation platform. Handles authentication, job orchestration, GCS signed URLs, and SSH-based model training/inference on a GCP VM.

## Tech Stack

- **FastAPI** 0.141 + Uvicorn
- **asyncpg** — Neon Postgres (serverless)
- **paramiko** — SSH to GCP VM for training/inference
- **google-cloud-storage** — Signed URL generation
- **bcrypt** — Password hashing
- **Pydantic v2** — Request/response validation

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /auth/register | Create account |
| POST | /auth/login | Get session token |
| POST | /auth/logout | Invalidate session |
| GET | /auth/me | Current user |
| GET | /models | List available models |
| GET | /jobs | List user's jobs |
| POST | /jobs/eval | Create inference job |
| POST | /jobs/finetune | Create finetune job |
| POST | /jobs/{id}/run-eval | Start inference |
| POST | /jobs/{id}/run-finetune | Start fine-tuning |
| GET | /jobs/{id}/results | Get predictions + metrics |
| GET | /jobs/{id}/download | Get checkpoint + script URLs |
| POST | /uploads/sign | Get GCS signed upload URLs |
| GET | /health | Health check |

## Local Development

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # Edit with your credentials
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| DATABASE_URL | Neon Postgres connection string |
| GCS_SA_KEY_PATH | GCS service account JSON (file path or inline JSON) |
| GCS_BUCKET_NAME | GCS bucket (default: terafac-datasets) |
| TRAINING_MODE | `stub` (fake) or `ssh` (real VM) |
| VM_HOST | GCP VM IP address |
| VM_USER | SSH username |
| VM_SSH_KEY_PATH | SSH private key (file path or inline key content) |

## Project Structure

```
backend/
├── src/
│   ├── main.py          # FastAPI app + lifespan
│   ├── auth.py          # Authentication routes + session management
│   ├── jobs.py          # Job CRUD + trigger routes
│   ├── training.py      # SSH eval/finetune execution + polling
│   ├── models.py        # Model registry from models.json
│   ├── uploads.py       # GCS signed URL generation
│   ├── gcs.py           # GCS client (supports inline JSON credentials)
│   ├── db.py            # asyncpg pool + table creation
│   └── config.py        # Pydantic settings
├── models.json          # Model registry (4 models)
├── requirements.txt
└── .env.example
```
