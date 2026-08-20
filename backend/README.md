# TERAFAC Backend

FastAPI backend for the TERAFAC agentic training pipeline.
**Phase 1 scope:** FE → BE → Firestore, hardcoded auth, inline stubs.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.12+ (`python --version`) |
| PowerShell | 5.1+ (built into Windows) |

---

## One-time setup

Run these **once** from `D:\TERAFAC\AGENTIC-UI\backend\`:

```powershell
# 0. Allow local scripts to run (only needed once per machine)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 1. Create the virtual environment (generates Activate.ps1, activate.bat, python.exe, pip.exe, etc.)
python -m venv venv

# 2. Upgrade pip inside the venv
.\venv\Scripts\python.exe -m pip install --upgrade pip

# 3. Install all runtime + dev dependencies
.\venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt
```

---

## Every session — activate the venv

**Option A — PowerShell (recommended):**
```powershell
cd D:\TERAFAC\AGENTIC-UI\backend
.\venv\Scripts\Activate.ps1
```
Your prompt becomes `(venv) PS D:\TERAFAC\AGENTIC-UI\backend>`.

**Option B — CMD / if Activate.ps1 is blocked:**
```cmd
cd D:\TERAFAC\AGENTIC-UI\backend
venv\Scripts\activate.bat
```

**If `Activate.ps1` gives "not recognized" or a security error:**
```powershell
# Fix execution policy once, then retry Activate.ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

**If the venv is missing or broken** (e.g. `Activate.ps1` does not exist):
```powershell
# Recreate it from scratch — deps reinstall in ~60s
Remove-Item -Recurse -Force venv
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt
.\venv\Scripts\Activate.ps1
```

Once active, all `python`, `pip`, `uvicorn`, `pytest`, and `ruff` commands use the venv automatically.

---

## Run the development server

```powershell
# venv must be active
uvicorn src.main:app --reload --port 8000
```

| URL | Description |
|-----|-------------|
| `http://localhost:8000/health` | Liveness probe → `{"status":"ok"}` |
| `http://localhost:8000/docs` | Swagger UI (interactive API docs) |
| `http://localhost:8000/openapi.json` | OpenAPI schema |

Stop the server with **Ctrl+C**.

---

## Environment variables

Copy `.env.example` to `.env` and edit your values:

```powershell
Copy-Item .env.example .env
notepad .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_TOKEN` | `dev-token-change-me` | Static Bearer token (Phase 1 auth) |
| `ADMIN_USERNAME` | `admin` | Username for `POST /auth/login` |
| `ADMIN_PASSWORD` | `admin` | Password for `POST /auth/login` |
| `CORS_ORIGINS` | `http://localhost:3100,...` | Comma-separated allowed FE origins |
| `FIRESTORE_PROJECT_ID` | `terafac-dev` | GCP project for Firestore |
| `PORT` | `8000` | Server port |

---

## Quality gates

Run all four **before every commit**, with the venv active:

```powershell
# 1. Lint
ruff check src/ tests/

# 2. Format check
ruff format --check src/ tests/

# 3. Tests
pytest tests/ -v

# 4. Server boot (manual)
uvicorn src.main:app --port 8000
# In another terminal:
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
# Expected: StatusCode 200, Content: {"status":"ok"}
```

---

## Updating dependencies

Whenever `requirements.txt` or `requirements-dev.txt` changes:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

---

## Rollback a milestone

```powershell
cd D:\TERAFAC\AGENTIC-UI\backend
git log --oneline
git reset --hard <milestone-sha>
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn src.main:app --reload --port 8000
```

---

## Project layout

```
backend/
  venv/                        ← virtual environment (gitignored)
  src/
    __init__.py
    main.py                    ← FastAPI app factory + lifespan
    config.py                  ← pydantic Settings (reads .env)
    middleware/
      auth.py                  ← Bearer token check (ADMIN_TOKEN)
      cors.py                  ← CORSMiddleware wiring
    routes/
      health.py                ← GET /health
    services/                  ← business logic (grows M1–M5)
    models/
      schemas.py               ← Pydantic request/response models (M1)
    db/
      firestore_client.py      ← Firestore client lazy singleton
      firestore_ops.py         ← CRUD helpers (M1)
  tests/
    conftest.py                ← fixtures: AsyncClient, auth_headers
    test_health.py             ← M0 tests (6 cases)
  requirements.txt
  requirements-dev.txt
  pyproject.toml               ← ruff + pytest + mypy config
  .env.example                 ← safe to commit
  .env                         ← your local secrets (gitignored)
  .gitignore
  README.md
```

---

## Phase roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **V1 — M0** | Scaffold: FastAPI, venv, health, auth middleware, Firestore client | ✅ |
| **V1 — M1** | Pydantic schemas + Firestore CRUD helpers | 🔲 |
| **V1 — M2** | Core job routes: POST /jobs, GET /jobs, GET /jobs/{id} | 🔲 |
| **V1 — M3** | Background task: pre_masking → awaiting_annotation auto-advance | 🔲 |
| **V1 — M4** | Job action routes: annotations, approve, reject, rerun | 🔲 |
| **V1 — M5** | Data routes: flagged, data-preview, compute, logs, results, inference | 🔲 |
| **V1 — M6** | Integration: FE wired to real BE, full flow verified | 🔲 |
| V2 | Real auth: bcrypt, Firestore sessions, rate-limit, quota | 🔲 |
| V3 | Broker + JWT hop tokens | 🔲 |
| V4 | Cloud Run, Vertex AI, GCS, Secret Manager | 🔲 |
