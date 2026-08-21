# TERAFAC Frontend

Next.js frontend for the TERAFAC segmentation platform. Provides user auth, model selection, image upload, job monitoring, and results visualization.

## Tech Stack

- **Next.js 16.3.0** (App Router, Turbopack)
- **React 19** + TypeScript 5.8 (strict)
- **Tailwind CSS v4** (CSS-first config)
- **Sonner** — Toast notifications
- **lucide-react** — Icons

## Pages

| Route | Purpose |
|-------|---------|
| /login | User sign-in |
| /register | User registration |
| / | Dashboard — list all jobs |
| /new-job | Create inference or finetune job |
| /jobs/[id] | Job detail — progress, metrics, predictions |

## Features

- Model category toggle (Object Mask / Edge Mask)
- GCS direct upload via signed PUT URLs
- Real-time job polling (3s interval)
- Pipeline step progress display
- Train/Val loss chart (inline SVG)
- Dynamic metrics display per model type
- Prediction image grid with overlay
- Checkpoint + inference script download

## Local Development

```bash
npm install
cp .env.example .env.local   # Set NEXT_PUBLIC_API_URL
npm run dev                  # Runs on port 3100
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| NEXT_PUBLIC_API_URL | Backend API URL (e.g. http://localhost:8000) |

## Build & Deploy

```bash
npm run build    # Production build (Turbopack)
npm run start    # Start production server
```

Deployed on **Vercel** — auto-deploys from `main` branch with root directory `frontend/`.

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx           # Root layout + AuthProvider
│   │   ├── page.tsx             # Dashboard (job list)
│   │   ├── login/page.tsx       # Login form
│   │   ├── register/page.tsx    # Register form
│   │   ├── new-job/page.tsx     # Create job (model select + upload)
│   │   └── jobs/[id]/page.tsx   # Job detail + results
│   ├── components/
│   │   ├── navbar.tsx           # Top navigation
│   │   ├── job-card.tsx         # Job list card
│   │   ├── loss-chart.tsx       # SVG train/val loss chart
│   │   └── protected.tsx        # Auth guard wrapper
│   └── lib/
│       ├── api.ts               # Typed API client
│       └── auth-context.tsx     # React context auth state
├── next.config.mjs
├── package.json
└── tsconfig.json
```
