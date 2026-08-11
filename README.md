# TERAFAC — Frontend (Next.js)

Frontend implementation of the **TERAFAC** agentic auto-training pipeline — a
single-user, cloud-hosted system for medical-mask annotation, model training, and
inference review, with a research + human-in-the-loop risk gate.

This is the complete, feature-complete V1 frontend. All eight milestones
(M0–M7) plus the final debug/cleanup pass are **done and verified**. The UI runs
against an in-browser mock backend (MSW) so the full pipeline can be exercised on
localhost with no server required.

> Full system design: see parent `BLOCKDIAGRAM.txt`. Milestone-by-milestone
> implementation detail lives in `../docs/frontendplan.md`.

---

## Tech Stack

| Area          | Choice                                                      |
| ------------- | ----------------------------------------------------------- |
| Framework     | **Next.js 16.3.0** (App Router, Turbopack)                  |
| React         | react 19.2.8 + react-dom 19.2.8                             |
| Language      | TypeScript 5.8.3 (strict)                                   |
| Styling       | Tailwind CSS v4.1.8 (CSS-first, no config file) + shadcn/ui |
| Charts        | Recharts 3.10.1                                             |
| State         | Zustand 5.0.14                                              |
| Annotation    | Custom canvas-based polygon annotator                        |
| Mock backend  | MSW 2.8.2 (Mock Service Worker)                              |
| Zip bundling  | JSZip 3.10.1                                                 |
| Notifications | Sonner 2.0.3                                                 |
| Icons         | lucide-react 0.487.0                                        |
| Package mgr   | npm 11.16.0 (Node 24.18.0)                                  |

---

## Project Structure

```
frontend/
├─ public/
│  ├─ mock-data/          # synthetic 64x64 PNGs (images/, flagged/)
│  ├─ mock-data/gen-images.cjs
│  └─ mockServiceWorker.js   # MSW browser worker
├─ src/
│  ├─ app/
│  │  ├─ layout.tsx          # dark html + <MswStarter> wrapper
│  │  ├─ page.tsx            # single URL "/" -> <JobShell>
│  │  ├─ api/save-mask/route.ts   # real Next route: mask persistence
│  │  └─ debug/page.tsx      # "/debug" — one-click endpoint sweep
│  ├─ components/
│  │  ├─ JobShell.tsx        # tab shell + StageBanner + polling
│  │  ├─ Annotator.tsx       # custom polygon mask annotator
│  │  ├─ MswStarter.tsx      # lazy MSW loader
│  │  ├─ StageBanner.tsx     # live stage banner
│  │  ├─ ApprovalModal.tsx   # risk-tier human approval gate
│  │  ├─ charts/             # Recharts components (VRAM, GPU, loss, metrics, log tail)
│  │  ├─ tabs/               # Job / Train / Annotate / Data / Compute / Logs / Results / Inference
│  │  └─ ui/                 # shadcn-style primitives
│  ├─ lib/
│  │  ├─ api.ts              # typed fetch client (mock vs prod routing)
│  │  ├─ annotator-coco.ts   # COCO polygon conversion
│  │  └─ polling.ts          # useJobPolling hook (3s, backoff)
│  ├─ mocks/                 # MSW browser + handlers (13 endpoints)
│  ├─ store/                 # Zustand stores (jobStore, navStore)
│  ├─ types/                 # job.ts, metrics.ts, coco.ts
│  └─ middleware.ts          # (if present)
```

Mutable mask data is written to `temp/{jobId}/masks/{imageId}.json` (git-ignored).

---

## Getting Started

### Prerequisites

- Node 24+ (developed on **v24.18.0**)
- npm 11+

### Environment

Copy and adjust as needed:

```bash
cp .env.example .env.local
```

- `NEXT_PUBLIC_USE_MOCK=true` → use the in-browser MSW mock backend (default for dev)
- `NEXT_PUBLIC_API_BASE` → real FastAPI backend base when `NEXT_PUBLIC_USE_MOCK=false`

### Install

A clean install is ~9–16 minutes on a slow filesystem; be patient and let it
finish. `.npmrc` keeps `legacy-peer-deps=true` (required by the eslint-plugin-react
peer chain) and adds fetch timeouts so installs don't hang on the registry.

```bash
npm install
```

### Run the dev server

```bash
npm run dev -- -p 3100
```

Open **http://localhost:3100/** — you'll see the 8-tab `JobShell`
(Jobs · Train · Annotate · Data · Compute · Logs · Results · Inference) with a
live stage banner. A brief "starting mock backend..." overlay clears once MSW
registers.

---

## End-to-End Usage (mock)

1. **Train** tab → enter a prompt → pick any `.zip` → watch the upload bar fill
   → click **Start job**.
2. Auto-navigates to the **Annotate** tab → draw polygon masks on the 4 flagged
   images → **Save Mask** per image (persists to `temp/` and ticks the M/N
   counter) → **Start Training**.
   - _Edit mode was intentionally removed in the final pass — annotate flow is
     simply **draw + Save Mask**._
3. The **ApprovalModal** auto-opens on the `awaiting_approval` stage → **Approve**
   to proceed (or **Reject** to halt).
4. During `training`: **Logs** (loss/metrics/log tail), **Compute**
   (VRAM/GPU/quota), **Data** (preview grid) all stream live.
5. At `done`: **Results** (metrics + sample predictions + risk banner) and
   **Inference** (script + checkpoint download) populate.
6. Use **"/debug"** (`http://localhost:3100/debug`) to hit all 13 mock endpoints
   in one click for quick verification.

---

## Verification Steps

These are the **official gates**. Run them **in order** from `frontend/`.

```powershell
cd D:\TERAFAC\AGENTIC-UI\frontend

# 1. Zero vulnerabilities
npm audit --no-fund
# expected: "found 0 vulnerabilities" (514 packages)

# 2. Lint clean
npm run lint
# expected: clean exit, 0 errors, 0 warnings

# 3. TypeScript strict typecheck
npm run typecheck
# expected: clean exit, 0 errors

# 4. Production build
npm run build
# expected: "Compiled successfully" (Next 16.3.0 Turbopack)
# routes: / (static), /_not-found (static), /debug (static), /api/save-mask (dynamic)
```

The dev-server smoke test is manual:

```powershell
npm run dev -- -p 3100
```

Expected: `Ready in <1s`, then http://localhost:3100 renders the tabbed JobShell,
the stage banner advances `pre_masking → awaiting_annotation → awaiting_approval
→ training → done`, charts populate, and the browser console is error-free.

---

## What Was Shipped (milestone summary)

- **M0 — Scaffold:** Next 16.3.0 + React 19 + TS strict + Tailwind v4 +
  shadcn/ui primitives (upgraded from Next 14 for CVE coverage). `daeb3b8`
- **M1 — Mock backend:** MSW with all **13 endpoints**, state-machine stage
  auto-advance, synthetic 64x64 PNGs, `/debug` page. `94485e6`
- **M2 — Tab shell + StageBanner + polling:** Zustand `jobStore`, `useJobPolling`
  (3s tick, exponential backoff), 8 real tab components. `e872f7a`
- **M3 — Jobs + Train tabs:** Jobs table + badge styling; Train form with upload
  progress, start-job flow → routes to Annotate. `851cac6`
- **M4 — Annotate tab:** custom canvas polygon annotator, per-image mask save to
  `temp/{jobId}/masks/`, live M/N counter, COCO conversion. `0d01bd4`
- **M5 — Data + Compute tabs:** 32-image preview grid; live VRAM gauge +
  GPU util line + quota cards (poll during `training`). `cd7eb57`
- **M6 — Logs + Results tabs:** loss/metrics charts, log tail, final metrics
  summary, sample-prediction triplets, risk-tier banner. `221aa79`
- **M7 — Inference + Approval modal:** inference script/code block + checkpoint
  download; auto-open approval Dialog with Approve/Reject. `1f21bb8`
- **Final debug —** fixed annotate Reset/progress "bounce" (job-scoped delete-all
  in `/api/save-mask`), removed Edit mode, swept all lint warnings to zero.
  `1f4b963`, `0b39c95`, `17bc24e`
- **Clean install + package hygiene:** removed unused `react-image-annotate`,
  refreshed lockfile (514 pkgs, 0 vulns), allowed native postinstall scripts,
  re-verified all gates. `a816f9c`, `94423af`

---

## Development Notes

- **Mock vs prod routing:** `src/lib/api.ts` uses `/api` when `NEXT_PUBLIC_USE_MOCK=true`,
  else `NEXT_PUBLIC_API_BASE`. Mask persistence is a real Next API route
  (`/api/save-mask`) regardless of mock mode.
- **Rollback:** each milestone is a single git commit. See `../docs/frontendplan.md`
  for per-milestone SHAs and `git reset --hard <sha>` instructions.