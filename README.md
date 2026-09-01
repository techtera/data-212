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

## CLI Usage (PowerShell)

All CLI commands below target the deployed platform. For local development, replace `$BACKEND` with `http://localhost:8000`.

### Setup
```powershell
$BACKEND = "https://terafac-backend.onrender.com"
# For local: $BACKEND = "http://localhost:8000"

# Register (first time only)
Invoke-RestMethod -Uri "$BACKEND/auth/register" -Method POST -ContentType "application/json" -Body '{"username":"cliuser","email":"cli@test.com","password":"test1234"}'

# Login
$login = Invoke-RestMethod -Uri "$BACKEND/auth/login" -Method POST -ContentType "application/json" -Body '{"username":"testuser","password":"testuser"}'
$TOKEN = $login.token

# Health check
Invoke-RestMethod -Uri "$BACKEND/health"

# List all models
$models = Invoke-RestMethod -Uri "$BACKEND/models" -Headers @{Authorization="Bearer $TOKEN"}
$models | ForEach-Object { $_.model_name }
```

### Run Inference
```powershell
# 1. List available models
$models = Invoke-RestMethod -Uri "$BACKEND/models" -Headers @{Authorization="Bearer $TOKEN"}
$models | Where-Object { $_.is_agent -ne $true } | Select-Object model_name, category

# 2. Get signed upload URLs
$urls = Invoke-RestMethod -Uri "$BACKEND/uploads/sign" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"job_name":"cli-infer-test"}'

# 3. Upload images
Invoke-WebRequest -Uri $urls.images_upload_url -Method PUT -ContentType "application/zip" -InFile "objectimages.zip"

# 4. Create eval job (choose from list above)
$job = Invoke-RestMethod -Uri "$BACKEND/jobs/eval" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"model_name":"YOLO11L-MASKING-MODEL","name":"cli-infer-test"}'
$JOB_ID = $job.id

# 5. Start inference
Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/run-eval" -Method POST -Headers @{Authorization="Bearer $TOKEN"}

# 6. Poll status (run repeatedly until status = "done")
$jobs = Invoke-RestMethod -Uri "$BACKEND/jobs" -Headers @{Authorization="Bearer $TOKEN"}
$jobs | Where-Object { $_.id -eq $JOB_ID } | Select-Object name, status

# 7. Save results to file (signed URLs are too long for terminal)
$results = Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/results" -Headers @{Authorization="Bearer $TOKEN"}
$results | ConvertTo-Json -Depth 10 | Out-File "infer-results.json"
Write-Host "Predictions: $($results.prediction_urls.Count) images"
```

### Run Fine-tuning
```powershell
# 1. List available models
$models = Invoke-RestMethod -Uri "$BACKEND/models" -Headers @{Authorization="Bearer $TOKEN"}
$models | Where-Object { $_.is_agent -ne $true } | Select-Object model_name, category

# 2. Upload images + masks
$urls = Invoke-RestMethod -Uri "$BACKEND/uploads/sign" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"job_name":"cli-ft-test"}'
Invoke-WebRequest -Uri $urls.images_upload_url -Method PUT -ContentType "application/zip" -InFile "objectimages.zip" -UseBasicParsing
Invoke-WebRequest -Uri $urls.masks_upload_url -Method PUT -ContentType "application/zip" -InFile "objectmasks.zip" -UseBasicParsing

# 3. Create finetune job (choose from list above)
#    Default params: YOLO(60ep,lr=1e-4) UNETPP(40ep,lr_enc=1e-5,lr_dec=5e-5) VGGT-SEG(2ep,lr=1e-4) VGGT-UNETPP(2ep,lr=3e-4)
$job = Invoke-RestMethod -Uri "$BACKEND/jobs/finetune" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"model_name":"YOLO11L-MASKING-MODEL","name":"cli-ft-test","epochs":10,"lr":0.0005}'
$JOB_ID = $job.id

# 4. Start training
Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/run-finetune" -Method POST -Headers @{Authorization="Bearer $TOKEN"}

# 5. Poll status (run repeatedly until status = "done" or "error")
$jobs = Invoke-RestMethod -Uri "$BACKEND/jobs" -Headers @{Authorization="Bearer $TOKEN"}
$jobs | Where-Object { $_.id -eq $JOB_ID } | Select-Object name, status

# 6. Save results to file
$results = Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/results" -Headers @{Authorization="Bearer $TOKEN"}
$results | ConvertTo-Json -Depth 10 | Out-File "ft-results.json"
Write-Host "Mean IoU: $($results.mean_iou) | Dice: $($results.dice_score) | Pixel Acc: $($results.pixel_accuracy)"

# 7. Download checkpoint (URL expires in 15 min)
$download = Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/download" -Headers @{Authorization="Bearer $TOKEN"}
Invoke-WebRequest -Uri $download.checkpoint_url -OutFile "best_checkpoint.pt" -UseBasicParsing
```

### AI Agent Training
```powershell
# 1. List existing agent models
$models = Invoke-RestMethod -Uri "$BACKEND/models" -Headers @{Authorization="Bearer $TOKEN"}
$models | Where-Object { $_.is_agent -eq $true } | Select-Object model_name, category, load_path

# 2. Research — AI suggests architecture
$research = Invoke-RestMethod -Uri "$BACKEND/research" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"prompt":"Need edge detection for weld seams on steel pipes"}'
$REPORT = $research.report
Write-Host $REPORT

# 3. Generate training code
$body = @{report=$REPORT.Substring(0,2000); job_name="cli-agent"; mask_type="edge"} | ConvertTo-Json
$code = Invoke-RestMethod -Uri "$BACKEND/coding/generate-train" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body $body
$MODEL = $code.model_name

# 4. Upload data
$urls = Invoke-RestMethod -Uri "$BACKEND/uploads/sign" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"job_name":"cli-agent"}'
Invoke-WebRequest -Uri $urls.images_upload_url -Method PUT -ContentType "application/zip" -InFile "edgeimages.zip"
Invoke-WebRequest -Uri $urls.masks_upload_url -Method PUT -ContentType "application/zip" -InFile "edgemasks.zip"

# 4. Create job + start agent training (auto-retries up to 10x on failure)
$body2 = @{model_name=$MODEL; name="cli-agent"} | ConvertTo-Json
$job = Invoke-RestMethod -Uri "$BACKEND/jobs/finetune" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body $body2
$JOB_ID = $job.id
Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/run-agent-train" -Method POST -Headers @{Authorization="Bearer $TOKEN"}

# 5. Poll status (run repeatedly until status = "done")
$jobs = Invoke-RestMethod -Uri "$BACKEND/jobs" -Headers @{Authorization="Bearer $TOKEN"}
$jobs | Where-Object { $_.id -eq $JOB_ID } | Select-Object name, status

# 6. Save results to file
$results = Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/results" -Headers @{Authorization="Bearer $TOKEN"}
$results | ConvertTo-Json -Depth 10 | Out-File "agent-train-results.json"
Write-Host "Mean IoU: $($results.mean_iou) | Dice: $($results.dice_score) | Pixel Acc: $($results.pixel_accuracy)"
```

### AI Agent Inference
```powershell
# 1. List agent models ready for inference (must have checkpoint from completed training)
$models = Invoke-RestMethod -Uri "$BACKEND/models" -Headers @{Authorization="Bearer $TOKEN"}
$agentModels = $models | Where-Object { $_.is_agent -eq $true -and $_.load_path -ne "" }
$agentModels | ForEach-Object { Write-Host "$($_.model_name) ($($_.category))" }

# 2. Pick model from list above
$MODEL = "agent-train_agent_v_1"

# 3. Generate inference code — AI writes script based on training code
$body = @{model_name=$MODEL} | ConvertTo-Json
Invoke-RestMethod -Uri "$BACKEND/coding/generate-inference" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body $body

# 4. Upload images (no masks needed)
$urls = Invoke-RestMethod -Uri "$BACKEND/uploads/sign" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"job_name":"cli-agent-infer"}'
Invoke-WebRequest -Uri $urls.images_upload_url -Method PUT -ContentType "application/zip" -InFile "edgeimages.zip"

# 5. Create job + start agent inference (auto-retries up to 10x)
$job = Invoke-RestMethod -Uri "$BACKEND/jobs/eval" -Method POST -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body "{`"model_name`":`"$MODEL`",`"name`":`"cli-agent-infer`"}"
$JOB_ID = $job.id
Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/run-agent-inference" -Method POST -Headers @{Authorization="Bearer $TOKEN"}

# 6. Poll status (run repeatedly until status = "done")
$jobs = Invoke-RestMethod -Uri "$BACKEND/jobs" -Headers @{Authorization="Bearer $TOKEN"}
$jobs | Where-Object { $_.id -eq $JOB_ID } | Select-Object name, status

# 7. Save results to file
$results = Invoke-RestMethod -Uri "$BACKEND/jobs/$JOB_ID/results" -Headers @{Authorization="Bearer $TOKEN"}
$results | ConvertTo-Json -Depth 10 | Out-File "agent-infer-results.json"
Write-Host "Predictions: $($results.prediction_urls.Count) images"
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
