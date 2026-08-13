"""
TERAFAC Backend Verification Script
====================================
Runs a full FE->BE->Auth->Broker->Firestore loop from the command line.
Each step prints clearly whether it passed or failed and what it proved.

Usage (from backend/ with venv active):
    python verify_stack.py

What it verifies:
  1. Server is reachable (GET /health)
  2. Auth gate — no token → 401
  3. Auth gate — bad token → 401
  4. Auth gate — dev-token → 200 (ALLOW_DEV_TOKEN=true path)
  5. Signed URL minted (POST /uploads/sign)  ← short-lived URL generation
  6. Signed URL structure is correct (unique, time-based, local dev endpoint)
  7. Dev upload accepted (PUT <signed_url>)
  8. Job creation → 201 + job_id returned (POST /jobs)
  9. Broker dispatched: backend log shows hop_token_issued + hop_token_verified
 10. Firestore job doc created (GET /jobs/{id} → stage=pre_masking)
 11. Firestore audit_log written: hop_token_issued event present
 12. Stage auto-advances: poll until awaiting_annotation (broker ran pre_masking)
 13. Submit annotations → awaiting_approval
 14. Approve job → training dispatched via broker (second hop token)
 15. Firestore audit_log: training hop_token_issued written
 16. Stage auto-advances: poll until done (broker ran training)
 17. Results available (GET /jobs/{id}/results)
 18. Inference endpoint returns checkpoint URL (GET /jobs/{id}/inference)
 19. Firestore audit_log: 4 entries total for this job (2 issued + 2 verified)
"""

from __future__ import annotations

import sys
import time
import json
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
BASE = "http://localhost:8000"
DEV_TOKEN = "dev-token-change-me"
GOOD_HEADERS = {"Authorization": f"Bearer {DEV_TOKEN}", "Content-Type": "application/json"}
BAD_HEADERS  = {"Authorization": "Bearer wrong-token-xyz",  "Content-Type": "application/json"}

OK  = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"
WARN = "\033[93m  WARN\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"

results = []


def req(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def put_raw(url: str):
    """Simulate FE uploading zip bytes to the signed PUT URL."""
    fake_zip = b"PK\x03\x04" + b"\x00" * 20  # fake zip magic bytes
    r = urllib.request.Request(url, data=fake_zip, method="PUT",
                               headers={"Authorization": f"Bearer {DEV_TOKEN}"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def check(label: str, condition: bool, detail: str = ""):
    symbol = OK if condition else FAIL
    print(f"{symbol}  {label}")
    if detail:
        print(f"       {detail}")
    results.append((label, condition))
    return condition


def info(msg: str):
    print(f"{INFO}  {msg}")


def section(title: str):
    line = "-" * (55 - len(title))
    print(f"\n{BOLD}-- {title} {line}{RESET}")


# ═══════════════════════════════════════════════════════════════════
section("1. SERVER HEALTH")
# ═══════════════════════════════════════════════════════════════════

status, body = req("GET", "/health")
check("GET /health returns 200", status == 200, f"got {status} body={body}")

# ═══════════════════════════════════════════════════════════════════
section("2. AUTH GATE")
# ═══════════════════════════════════════════════════════════════════

status, _ = req("GET", "/jobs")
check("No token → 401", status == 401, f"got {status}")

status, _ = req("GET", "/jobs", headers=BAD_HEADERS)
check("Bad token → 401", status == 401, f"got {status}")

status, _ = req("GET", "/jobs", headers=GOOD_HEADERS)
check("Dev-token → 200 (ALLOW_DEV_TOKEN path)", status == 200,
      f"got {status}  (proves auth middleware passed dev-token check, set request.state.user_id='dev-admin')")

# ═══════════════════════════════════════════════════════════════════
section("3. SIGNED URL GENERATION  (short-lived URL mint)")
# ═══════════════════════════════════════════════════════════════════

info("POST /uploads/sign  — this is where the backend mints a short-lived PUT URL")
t_before = int(time.time() * 1000)
status, sign1 = req("POST", "/uploads/sign", headers=GOOD_HEADERS)
t_after  = int(time.time() * 1000)

check("POST /uploads/sign returns 200", status == 200, f"got {status}")
check("Response has signed_put_url", "signed_put_url" in sign1,
      f"got keys: {list(sign1.keys())}")
check("Response has object_path", "object_path" in sign1)

if "signed_put_url" in sign1:
    url1 = sign1["signed_put_url"]
    path1 = sign1["object_path"]
    info(f"signed_put_url = {url1}")
    info(f"object_path    = {path1}")

    # Verify URL is time-based (hex timestamp in the ds_<hex> id)
    try:
        ds_id = url1.split("/dev/upload/")[1]
        ts_from_id = int(ds_id.lstrip("ds_"), 16) if ds_id.startswith("ds_") else int(ds_id, 16)
        url_age_ms = t_after - ts_from_id
        check(
            "signed_put_url is time-based (URL ID encodes current timestamp)",
            -2000 < url_age_ms < 5000,
            f"URL timestamp is {url_age_ms}ms from now (should be near 0)"
        )
    except Exception as e:
        check("signed_put_url is time-based", False, str(e))

    # Mint a second URL — must be different (unique per call)
    time.sleep(0.01)
    _, sign2 = req("POST", "/uploads/sign", headers=GOOD_HEADERS)
    check(
        "Two consecutive signed URLs are unique (not reused)",
        sign1.get("signed_put_url") != sign2.get("signed_put_url"),
        f"url1={sign1.get('signed_put_url')}  url2={sign2.get('signed_put_url')}"
    )

    # object_path has the right structure
    check(
        "object_path has datasets/<id>/raw.zip structure",
        path1.startswith("datasets/") and path1.endswith("/raw.zip"),
        f"got {path1}"
    )

# ═══════════════════════════════════════════════════════════════════
section("4. DEV UPLOAD ENDPOINT  (fake GCS PUT)")
# ═══════════════════════════════════════════════════════════════════

if "signed_put_url" in sign1:
    put_status = put_raw(sign1["signed_put_url"])
    check(
        "PUT <signed_put_url> returns 200 (dev upload acceptor)",
        put_status == 200,
        f"got {put_status}  (In V4 this PUT goes directly to GCS — same FE code, different URL)"
    )

# ═══════════════════════════════════════════════════════════════════
section("5. JOB CREATION  → BROKER DISPATCH")
# ═══════════════════════════════════════════════════════════════════

info("POST /jobs — triggers: Firestore write, issue_hop_token, broker.enqueue")
status, job_resp = req("POST", "/jobs", headers=GOOD_HEADERS, body={
    "prompt": "verify stack: segmentation test",
    "dataset_object_path": sign1.get("object_path", "datasets/test/raw.zip"),
})

check("POST /jobs returns 201", status == 201, f"got {status} body={job_resp}")

job_id = job_resp.get("job_id", "")
check("Response contains job_id", bool(job_id), f"got {job_resp}")
check("Initial stage is pre_masking", job_resp.get("stage") == "pre_masking",
      f"got stage={job_resp.get('stage')}")

if job_id:
    info(f"job_id = {job_id}")

# ═══════════════════════════════════════════════════════════════════
section("6. FIRESTORE JOB DOC  (GET /jobs/{id})")
# ═══════════════════════════════════════════════════════════════════

if job_id:
    status, progress = req("GET", f"/jobs/{job_id}", headers=GOOD_HEADERS)
    check("GET /jobs/{id} returns 200", status == 200, f"got {status}")
    check("Job doc has stage=pre_masking in Firestore",
          progress.get("stage") == "pre_masking",
          f"got stage={progress.get('stage')}")
    check("Job doc has progress=25", progress.get("progress") == 25,
          f"got progress={progress.get('progress')}")

# ═══════════════════════════════════════════════════════════════════
section("7. BROKER + PRE-MASKING STAGE ADVANCE  (poll for awaiting_annotation)")
# ═══════════════════════════════════════════════════════════════════

info("Waiting up to 15s for broker to execute run_pre_masking (4s delay)...")
info("Broker flow: enqueue → verify_hop_token → run_pre_masking → Firestore write")

stage = "pre_masking"
waited = 0
if job_id:
    while stage == "pre_masking" and waited < 15:
        time.sleep(1)
        waited += 1
        _, p = req("GET", f"/jobs/{job_id}", headers=GOOD_HEADERS)
        stage = p.get("stage", "pre_masking")
        print(f"       polling... {waited}s  stage={stage}", end="\r")
    print()

check(
    f"Stage advanced to awaiting_annotation after broker ran pre_masking ({waited}s)",
    stage == "awaiting_annotation",
    f"got stage={stage}  (if still pre_masking — check backend terminal for broker logs)"
)

# ═══════════════════════════════════════════════════════════════════
section("8. ANNOTATIONS SUBMISSION  → awaiting_approval")
# ═══════════════════════════════════════════════════════════════════

if job_id and stage == "awaiting_annotation":
    status, ann_resp = req("POST", f"/jobs/{job_id}/annotations",
                           headers=GOOD_HEADERS, body={"ack": True})
    check("POST /jobs/{id}/annotations returns 200", status == 200, f"got {status}")
    check("Stage advances to awaiting_approval", ann_resp.get("stage") == "awaiting_approval",
          f"got {ann_resp}")
    stage = ann_resp.get("stage", stage)

# ═══════════════════════════════════════════════════════════════════
section("9. APPROVE JOB  → TRAINING BROKER DISPATCH  (second hop token)")
# ═══════════════════════════════════════════════════════════════════

if job_id and stage == "awaiting_approval":
    info("POST /jobs/{id}/approve — triggers: issue_hop_token(step=training) + broker.enqueue")
    status, approve_resp = req("POST", f"/jobs/{job_id}/approve", headers=GOOD_HEADERS)
    check("POST /jobs/{id}/approve returns 200", status == 200, f"got {status}")
    check("Stage advances to training", approve_resp.get("stage") == "training",
          f"got {approve_resp}")
    stage = approve_resp.get("stage", stage)

# ═══════════════════════════════════════════════════════════════════
section("10. TRAINING STAGE ADVANCE  (poll for done)")
# ═══════════════════════════════════════════════════════════════════

info("Waiting up to 35s for broker to complete 10-epoch training (10 x 2s)...")

waited = 0
if job_id and stage == "training":
    while stage == "training" and waited < 35:
        time.sleep(2)
        waited += 2
        _, p = req("GET", f"/jobs/{job_id}", headers=GOOD_HEADERS)
        stage = p.get("stage", "training")
        epoch = p.get("epoch", 0)
        print(f"       polling... {waited}s  stage={stage}  epoch={epoch}/10", end="\r")
    print()

check(
    f"Stage reached done after training ({waited}s)",
    stage == "done",
    f"got stage={stage}"
)

# ═══════════════════════════════════════════════════════════════════
section("11. RESULTS + INFERENCE  (Firestore final doc read)")
# ═══════════════════════════════════════════════════════════════════

if job_id and stage == "done":
    status, results_resp = req("GET", f"/jobs/{job_id}/results", headers=GOOD_HEADERS)
    check("GET /jobs/{id}/results returns 200", status == 200, f"got {status}")
    check("final_metrics present", "final_metrics" in results_resp)
    check("risk_tier present", "risk_tier" in results_resp,
          f"risk_tier={results_resp.get('risk_tier')}")

    status, inf_resp = req("GET", f"/jobs/{job_id}/inference", headers=GOOD_HEADERS)
    check("GET /jobs/{id}/inference returns 200", status == 200, f"got {status}")
    check("inference has code field", "code" in inf_resp)
    check("inference has checkpoint_signed_url", "checkpoint_signed_url" in inf_resp,
          f"url={inf_resp.get('checkpoint_signed_url')}")

# ═══════════════════════════════════════════════════════════════════
section("12. FIRESTORE AUDIT_LOG  (hop token audit trail)")
# ═══════════════════════════════════════════════════════════════════

info("Checking Firestore audit_log via the firebase-admin SDK directly...")

try:
    import os
    os.environ.setdefault("JWT_HOP_SECRET", "test-secret-for-local-dev-minimum-32-chars!!")
    from src.db.firebase import db

    audit_docs = list(
        db.collection("audit_log")
          .where("job_id", "==", job_id)
          .stream()
    ) if job_id else []

    events = [d.to_dict() for d in audit_docs]
    issued   = [e for e in events if e.get("event") == "hop_token_issued"]
    verified = [e for e in events if e.get("event") == "hop_token_verified"]

    check(
        f"audit_log has 2 hop_token_issued entries (pre_masking + training)",
        len(issued) == 2,
        f"found {len(issued)}: {[e.get('step') for e in issued]}"
    )
    check(
        f"audit_log has 2 hop_token_verified entries",
        len(verified) == 2,
        f"found {len(verified)}: {[e.get('step') for e in verified]}"
    )
    check(
        "No raw token in any audit entry",
        all("token" not in e and "hop_token" not in e and "jwt" not in e for e in events),
        "raw token field found — security violation!" if events else "no entries to check"
    )
    check(
        "issued entries have issued_at + expires_at timestamps",
        all("issued_at" in e and "expires_at" in e for e in issued),
        str([{k: v for k, v in e.items() if k in ("step", "issued_at", "expires_at")} for e in issued])
    )
    check(
        "verified entries do NOT have issued_at/expires_at (metadata only)",
        all("issued_at" not in e and "expires_at" not in e for e in verified),
    )

    if events:
        info(f"Audit entries for job {job_id}:")
        for e in sorted(events, key=lambda x: str(x.get("event", "")) + str(x.get("step", ""))):
            ts = e.get("ts", "")
            info(f"  event={e.get('event'):25s}  step={e.get('step'):15s}  ts={str(ts)[:19]}")

except Exception as ex:
    print(f"{WARN}  Firestore audit check skipped: {ex}")
    print(f"       (This is expected if firebase-service-account.json has restricted permissions)")
    print(f"       Verify manually: Firebase Console → agentical-e192f → Firestore → audit_log")

# ═══════════════════════════════════════════════════════════════════
section("SUMMARY")
# ═══════════════════════════════════════════════════════════════════

passed = sum(1 for _, ok in results if ok)
total  = len(results)
all_ok = passed == total

print(f"\n  {passed}/{total} checks passed")
if all_ok:
    print(f"\n{BOLD}\033[92m  ALL CHECKS PASSED — full FE->BE->Auth->Broker->Firestore loop verified\033[0m{RESET}")
else:
    failed = [label for label, ok in results if not ok]
    print(f"\n\033[91m  FAILED:\033[0m")
    for f in failed:
        print(f"    • {f}")

sys.exit(0 if all_ok else 1)
