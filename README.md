# TERAFAC — Image Segmentation Fine-Tuning & Inference Platform

A full-stack platform for fine-tuning and running inference on image segmentation models. Users upload images (+ masks for fine-tuning), select a pretrained model, and get predictions or a fine-tuned checkpoint — all executed on a GPU server via SSH. Includes an AI Research Agent that suggests architectures and a Coding Agent that generates training code.

## Architecture

```
Frontend (Next.js 16, Vercel)  <-->  Backend (FastAPI, Render)  <-->  Neon DB (Postgres)
                                           |                              |
                                      GCS Bucket                    GCP VM (SSH)
                                   (uploads, results)            (GPU training/inference)
                                           |
                                    Gemini API (Research + Coding Agent)
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
- Image upload via GCS signed URLs (drag & drop)
- Inference with overlay predictions
- Fine-tuning with train/val metrics + interactive loss plot
- AI Research Agent (Gemini + grounded search) for architecture recommendation
- AI Coding Agent generates training code for new architectures
- Auto-debug loop: if training fails, AI fixes the code and retries
- Checkpoint download + user inference script
- Per-user GCS paths (no data collision)
- Apple HIG-inspired dark theme UI

## Local Development

### Prerequisites
- Python 3.9+
- Node.js 18+
- GCS service account JSON
- GCP VM with GPU (for training/inference)
- Gemini API key (for AI agents)

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
cp .env.example .env           # Edit with your credentials
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local     # Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3100

## CLI Usage (Command Line)

### Run Inference
```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' | jq -r .token)

# 2. Get signed upload URL
URLS=$(curl -s -X POST http://localhost:8000/uploads/sign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_name":"my-job"}')

# 3. Upload images
curl -X PUT "$(echo $URLS | jq -r .images_upload_url)" \
  -H "Content-Type: application/zip" --data-binary @images.zip

# 4. Create and run eval job
JOB=$(curl -s -X POST http://localhost:8000/jobs/eval \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name":"YOLO11L-MASKING-MODEL","name":"my-job"}')
JOB_ID=$(echo $JOB | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-eval" \
  -H "Authorization: Bearer $TOKEN"

# 5. Poll for results
curl -s "http://localhost:8000/jobs/$JOB_ID/results" \
  -H "Authorization: Bearer $TOKEN"
```

### Run Fine-tuning
```bash
# Same as above but upload masks too, use /jobs/finetune and /jobs/{id}/run-finetune
curl -X PUT "$(echo $URLS | jq -r .masks_upload_url)" \
  -H "Content-Type: application/zip" --data-binary @masks.zip

JOB=$(curl -s -X POST http://localhost:8000/jobs/finetune \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name":"UNETPLUSPLUS-MODEL","name":"my-job"}')
JOB_ID=$(echo $JOB | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-finetune" \
  -H "Authorization: Bearer $TOKEN"
```

### AI Agent Training (CLI)
```bash
# 1. Research architecture
REPORT=$(curl -s -X POST http://localhost:8000/research \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Need edge detection for weld seams on steel pipes"}' | jq -r .report)

# 2. Generate training code
CODE=$(curl -s -X POST http://localhost:8000/coding/generate-train \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"report\":\"$REPORT\",\"job_name\":\"weld-model\",\"mask_type\":\"edge\"}")
MODEL=$(echo $CODE | jq -r .model_name)

# 3. Upload data + start training
# ... same upload steps ...
JOB=$(curl -s -X POST http://localhost:8000/jobs/finetune \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"model_name\":\"$MODEL\",\"name\":\"weld-model\"}")
JOB_ID=$(echo $JOB | jq -r .id)

curl -X POST "http://localhost:8000/jobs/$JOB_ID/run-agent-train" \
  -H "Authorization: Bearer $TOKEN"

# 4. If training fails, debug with AI
curl -X POST http://localhost:8000/coding/debug \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\":\"$JOB_ID\",\"model_name\":\"$MODEL\",\"user_message\":\"masks are _mask.png format\"}"
```

## AI Agent Sample Prompts

Use these with the Research Agent to test architecture recommendations:

- "We need to segment welding seams and detect defects like porosity and cracks in steel pipe images captured by industrial cameras at 1280x720 resolution"
- "I have 500 aerial drone images of solar panels. Need to segment individual panel cells and detect micro-cracks on the surface"
- "Detect and segment individual products on a conveyor belt for quality control. Objects are metallic cylindrical parts with varying reflectivity"

## Deployment

- **Frontend**: Vercel (auto-deploys from `main`, root: `frontend/`)
- **Backend**: Render (auto-deploys from `main`, root: `backend/`)
- **Database**: Neon Postgres (serverless)
- **Storage**: Google Cloud Storage
- **Compute**: GCP VM with 2x A100 80GB GPUs

## Environment Variables

See `backend/.env.example` and `frontend/.env.example` for required configuration.
