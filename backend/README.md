# TERAFAC Backend

FastAPI backend for the TERAFAC segmentation platform. Handles authentication, job orchestration, GCS signed URLs, SSH-based training/inference, and AI agents (Research + Coding).

## Tech Stack

- **FastAPI** 0.141 + Uvicorn
- **asyncpg** — Neon Postgres (serverless)
- **paramiko** — SSH to GCP VM for training/inference
- **google-cloud-storage** — Signed URL generation
- **httpx** — Gemini API calls (Research + Coding agents)
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
| GET | /models/{name}/viz | Get model sample visualizations |
| GET | /jobs | List user's jobs |
| POST | /jobs/eval | Create inference job |
| POST | /jobs/finetune | Create finetune job |
| POST | /jobs/{id}/run-eval | Start inference (normal models) |
| POST | /jobs/{id}/run-finetune | Start fine-tuning (normal models) |
| POST | /jobs/{id}/run-agent-train | Start agent-generated training |
| GET | /jobs/{id}/results | Get predictions + metrics |
| GET | /jobs/{id}/download | Get checkpoint + script URLs |
| POST | /uploads/sign | Get GCS signed upload URLs |
| POST | /research | AI Research Agent (Gemini + grounded search) |
| GET | /research/report/{name} | Get research report signed URL |
| POST | /coding/generate-train | AI Coding Agent: generate training script |
| POST | /coding/generate-inference | AI Coding Agent: generate inference script |
| POST | /coding/debug | AI Coding Agent: fix failed script + retry |
| GET | /health | Health check |

## Project Structure

```
backend/
├── src/
│   ├── main.py              # FastAPI app + lifespan
│   ├── auth.py              # Authentication routes
│   ├── jobs.py              # Job CRUD + trigger routes
│   ├── models.py            # Model registry (models.json + user_models DB)
│   ├── uploads.py           # GCS signed URL generation
│   ├── gcs.py               # GCS client (supports inline JSON credentials)
│   ├── db.py                # asyncpg pool + table creation
│   ├── config.py            # Pydantic settings
│   ├── training.py          # Normal SSH eval/finetune (4 base models)
│   ├── training_agent.py    # Agent SSH training (AI-generated code)
│   ├── inference_agent.py   # Agent SSH inference (AI-generated code)
│   ├── research.py          # Research Agent (Gemini + grounded search)
│   └── coding.py            # Coding Agent (generate/debug training+inference)
├── architecture.json        # Model architecture specs for Research Agent
├── models.json              # Model registry (4 pretrained models)
├── requirements.txt
└── .env.example
```

## Local Development

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
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
| GEMINI_API_KEY | Google Gemini API key (for Research + Coding agents) |

## Adding New Models

Add entry to `models.json`:
```json
{
  "model_name": "YOUR-MODEL",
  "category": "object_mask",
  "load_path": "gs://bucket/checkpoint.pt",
  "inference_script": "gs://terafac-datasets/inference/code/your_inference.py",
  "finetune_script": "gs://terafac-datasets/finetune/code/your_finetune.py",
  "usr_inference_script": "gs://terafac-datasets/usr-inference-code/your_inference.py",
  "save_path": "",
  "user_id": ""
}
```

Scripts must accept: `--model-path`, `--images-dir`, `--masks-dir` (finetune), `--output-dir`, `--job-id`
