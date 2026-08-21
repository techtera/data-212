# TERAFAC — Image Segmentation Fine-Tuning & Inference Platform

A full-stack platform for fine-tuning and running inference on image segmentation models. Users upload images (+ masks for fine-tuning), select a pretrained model, and get predictions or a fine-tuned checkpoint — all executed on a GPU server via SSH.

## Architecture

```
Frontend (Next.js 16, Vercel)  <-->  Backend (FastAPI, Render)  <-->  Neon DB (Postgres)
                                           |                              |
                                      GCS Bucket                    GCP VM (SSH)
                                   (uploads, results)            (GPU training/inference)
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
- Image upload via GCS signed URLs
- Inference with overlay predictions
- Fine-tuning with train/val metrics + loss plot
- Checkpoint download + user inference script
- Per-user GCS paths (no data collision)

## Deployment

- **Frontend**: Vercel (deploys from `main` branch, root: `frontend/`)
- **Backend**: Render (deploys from `main` branch, root: `backend/`)
- **Database**: Neon Postgres (serverless)
- **Storage**: Google Cloud Storage
- **Compute**: GCP VM with GPU (SSH-based job execution)

## Local Development

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000 --host 0.0.0.0

# Frontend
cd frontend
npm install
npm run dev
```

## Environment Variables

See `backend/.env.example` and `frontend/.env.example` for required configuration.
