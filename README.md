# TERAFAC — Image Segmentation Fine-Tuning & Inference Platform

A full-stack platform for fine-tuning and running inference on image segmentation models. Users upload images (+ masks for fine-tuning), select a pretrained model, and get predictions or a fine-tuned checkpoint — all executed on a GPU server via SSH. Includes an AI Research Agent that suggests architectures and a Coding Agent that generates training code.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/techtera/data-212.git
cd data-212

# 2. Setup Backend
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
cp .env.example .env           # Edit .env with your credentials (see below)
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0

# 3. Setup Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local     # Edit if needed
npm run dev
```

Open http://localhost:3100 — register an account and start using the platform.

## Environment Setup

### Backend (`backend/.env`)

| Variable | Required | How to get it |
|----------|----------|---------------|
| `DATABASE_URL` | Yes | Create free DB at [neon.tech](https://neon.tech), copy connection string |
| `GCS_SA_KEY_PATH` | Yes | GCP Console → IAM → Service Accounts → Create key (JSON). Put file in `backend/` |
| `GCS_BUCKET_NAME` | Yes | Create a GCS bucket (default: `terafac-datasets`) |
| `VM_HOST` | For SSH mode | GCP VM external IP |
| `VM_USER` | For SSH mode | VM SSH username |
| `VM_SSH_KEY_PATH` | For SSH mode | Path to ed25519 private key (or paste key content for Render) |
| `TRAINING_MODE` | Yes | `stub` (no VM, fake results) or `ssh` (real GPU training) |
| `GEMINI_API_KEY` | For AI agents | Get free key at [ai.google.dev](https://ai.google.dev) |

**For local dev without a GPU VM:** Set `TRAINING_MODE=stub` — all training/inference returns fake results after 5-10s delay. No VM needed.

### Frontend (`frontend/.env.local`)

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` (local) or your deployed backend URL |

## Architecture

```
Frontend (Next.js 16)  <-->  Backend (FastAPI)  <-->  Neon DB (Postgres)
                                    |                       |
                               GCS Bucket              GCP VM (SSH)
                            (uploads, results)       (GPU training/inference)
                                    |
                             Gemini API
                        (Research + Coding Agent)
```

## Models

| Model | Category | Task |
|-------|----------|------|
| YOLO11L-MASKING-MODEL | Object Mask | Instance segmentation |
| VGGT-SEGFORMER | Object Mask | Semantic segmentation (ViT-Large + SegFormer) |
| UNETPLUSPLUS-MODEL | Edge Mask | Edge detection (EfficientNet-B3 + UNet++) |
| VGGT-UNETPP | Edge Mask | Edge detection (ViT-Large + UNet++) |

## Features

- User authentication (bcrypt + session tokens)
- Model category selector (Object Mask / Edge Mask)
- Model info cards with sample I/O visualizations
- Image upload via GCS signed URLs (drag & drop)
- Inference with overlay predictions
- Fine-tuning with train/val metrics + interactive loss plot
- AI Research Agent (Gemini + grounded search) for architecture recommendation
- AI Coding Agent generates training code for new architectures
- Auto-debug: if training fails, AI fixes the code and retries
- Checkpoint download + view training code
- Per-user GCS paths (no data collision)
- Apple HIG-inspired dark theme UI

## CLI Usage

### Login
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"myuser","password":"mypass"}' | jq -r .token)
```

### Run Inference
```bash
# Get upload URL
URLS=$(curl -s -X POST http://localhost:8000/uploads/sign \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"job_name":"my-job"}')

# Upload images
curl -X PUT "$(echo $URLS | jq -r .images_upload_url)" \
  -H "Content-Type: application/zip" --data-binary @images.zip

# Create + run
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs/eval \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_name":"YOLO11L-MASKING-MODEL","name":"my-job"}' | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-eval" \
  -H "Authorization: Bearer $TOKEN"

# Poll results
curl -s "http://localhost:8000/jobs/$JOB_ID/results" -H "Authorization: Bearer $TOKEN"
```

### Run Fine-tuning
```bash
# Upload masks too
curl -X PUT "$(echo $URLS | jq -r .masks_upload_url)" \
  -H "Content-Type: application/zip" --data-binary @masks.zip

JOB_ID=$(curl -s -X POST http://localhost:8000/jobs/finetune \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_name":"UNETPLUSPLUS-MODEL","name":"my-job"}' | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-finetune" \
  -H "Authorization: Bearer $TOKEN"
```

### AI Agent Training (CLI)
```bash
# 1. Research
REPORT=$(curl -s -X POST http://localhost:8000/research \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"prompt":"Need edge detection for weld seams on steel pipes"}' | jq -r .report)

# 2. Generate code
MODEL=$(curl -s -X POST http://localhost:8000/coding/generate-train \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"report\":\"$REPORT\",\"job_name\":\"weld-model\",\"mask_type\":\"edge\"}" | jq -r .model_name)

# 3. Upload data + start agent training
# ... upload images.zip + masks.zip as above ...
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs/finetune \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"model_name\":\"$MODEL\",\"name\":\"weld-model\"}" | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-agent-train" \
  -H "Authorization: Bearer $TOKEN"

# 4. If fails, debug with AI
curl -X POST http://localhost:8000/coding/debug \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"job_id\":\"$JOB_ID\",\"model_name\":\"$MODEL\",\"user_message\":\"masks are _mask.png format\"}"
```

## AI Agent Sample Prompts

- "We need to segment welding seams and detect defects like porosity and cracks in steel pipe images captured by industrial cameras at 1280x720 resolution"
- "I have 500 aerial drone images of solar panels. Need to segment individual panel cells and detect micro-cracks on the surface"
- "Detect and segment individual products on a conveyor belt for quality control. Objects are metallic cylindrical parts with varying reflectivity"

## Deployment

- **Frontend**: [Vercel](https://vercel.com) — auto-deploys from `main`, root: `frontend/`
- **Backend**: [Render](https://render.com) — auto-deploys from `main`, root: `backend/`
- **Database**: [Neon](https://neon.tech) — serverless Postgres
- **Storage**: Google Cloud Storage
- **Compute**: GCP VM with 2x A100 80GB GPUs
