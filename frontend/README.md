# TERAFAC Frontend

Next.js frontend for the TERAFAC segmentation platform. Provides user auth, model selection, image upload, job monitoring, results visualization, and AI Agent training interface.

## Tech Stack

- **Next.js 16.3.0** (App Router, Turbopack)
- **React 19** + TypeScript 5.8 (strict)
- **Tailwind CSS v4** (CSS-first config, Apple HIG dark theme)
- **Sonner** — Toast notifications
- **lucide-react** — Icons

## Pages

| Route | Purpose |
|-------|---------|
| /login | User sign-in |
| /register | User registration |
| / | Dashboard — list all jobs (3-column grid) |
| /new-job | Create inference or finetune job (with/without AI agent) |
| /jobs/agent-train | AI Agent training flow (research → upload → train) |
| /jobs/[id] | Job detail — progress, metrics, predictions, debug |

## Features

- Model category toggle (Object Mask / Edge Mask)
- Model info cards with sample I/O visualizations
- GCS direct upload via signed PUT URLs (click + drag & drop)
- Real-time job polling (3s interval)
- Pipeline step progress display (distinct for inference/finetune)
- Train/Val loss chart (interactive SVG with hover tooltips)
- Colorful training summary with gradient stat cards + metrics table
- Prediction image grid with overlay
- Checkpoint download + view training code
- AI Research Agent (describes task → gets architecture report)
- AI Coding Agent (generates training code, auto-debug on failure)
- "Fix & Retry" button with optional user hint for debugging
- Apple HIG-inspired design: backdrop blur navbar, rounded-2xl cards, gradient buttons

## Local Development

```bash
npm install
cp .env.example .env.local   # Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                  # Runs on port 3100
```

Open http://localhost:3100

## Environment Variables

| Variable | Purpose |
|----------|---------|
| NEXT_PUBLIC_API_URL | Backend API URL (e.g. http://localhost:8000 or https://your-backend.onrender.com) |

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
│   │   ├── layout.tsx              # Root layout + AuthProvider + Toaster
│   │   ├── globals.css             # Tailwind + theme (Apple HIG dark)
│   │   ├── page.tsx                # Dashboard (3-col job grid)
│   │   ├── login/page.tsx          # Frosted glass login card
│   │   ├── register/page.tsx       # Registration
│   │   ├── new-job/page.tsx        # Create job (model select + upload)
│   │   └── jobs/
│   │       ├── [id]/page.tsx       # Job detail + metrics + predictions
│   │       └── agent-train/page.tsx # AI Agent training flow
│   ├── components/
│   │   ├── navbar.tsx              # Sticky backdrop-blur nav
│   │   ├── job-card.tsx            # Job list card (gradient icons)
│   │   ├── loss-chart.tsx          # Interactive SVG loss chart
│   │   ├── model-info-card.tsx     # Model sample I/O + description
│   │   └── protected.tsx           # Auth guard wrapper
│   └── lib/
│       ├── api.ts                  # Typed API client (all endpoints)
│       └── auth-context.tsx        # React context auth state
├── next.config.mjs
├── package.json
└── tsconfig.json
```
