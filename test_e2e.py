"""End-to-end test script for the TERAFAC pipeline.

Exercises: register → login → sign upload → PUT images.zip + masks.zip → create eval job → run → poll → results.

Usage:
    python test_e2e.py [--base-url http://localhost:8000] [--images path/to/images.zip] [--masks path/to/masks.zip]

If --images/--masks are not provided, creates tiny dummy zips.
"""

import argparse
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_URL = "http://localhost:8000"


def make_dummy_zip(name: str = "dummy.png") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="TERAFAC E2E test")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--images", type=Path, help="Path to images.zip")
    parser.add_argument("--masks", type=Path, help="Path to masks.zip")
    parser.add_argument("--username", default="testuser_e2e")
    parser.add_argument("--password", default="TestPass123!")
    parser.add_argument("--email", default="test_e2e@example.com")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Base URL: {base}")

    # --- Health check ---
    r = requests.get(f"{base}/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("[OK] Health check passed")

    # --- Register (ignore 409 if already exists) ---
    r = requests.post(f"{base}/auth/register", json={
        "username": args.username,
        "email": args.email,
        "password": args.password,
    })
    if r.status_code == 201:
        print(f"[OK] Registered user: {args.username}")
    elif r.status_code == 409:
        print(f"[OK] User already exists: {args.username}")
    else:
        print(f"[ERR] Register failed: {r.status_code} {r.text}")
        return

    # --- Login ---
    r = requests.post(f"{base}/auth/login", json={
        "username": args.username,
        "password": args.password,
    })
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data["token"]
    user_id = data["user"]["id"]
    print(f"[OK] Logged in as {args.username} (id={user_id})")

    headers = {"Authorization": f"Bearer {token}"}

    # --- Get /auth/me ---
    r = requests.get(f"{base}/auth/me", headers=headers)
    assert r.status_code == 200
    print(f"[OK] /auth/me: {r.json()['username']}")

    # --- Sign upload URLs ---
    r = requests.post(f"{base}/uploads/sign", headers=headers)
    assert r.status_code == 200, f"Sign failed: {r.status_code} {r.text}"
    sign_data = r.json()
    dataset_id = sign_data["dataset_id"]
    images_url = sign_data["images_upload_url"]
    masks_url = sign_data["masks_upload_url"]
    print(f"[OK] Signed URLs for dataset_id={dataset_id}")

    # --- Upload images.zip ---
    if args.images and args.images.exists():
        images_bytes = args.images.read_bytes()
        print(f"     Using real images: {args.images} ({len(images_bytes)} bytes)")
    else:
        images_bytes = make_dummy_zip("images/test001.png")
        print(f"     Using dummy images.zip ({len(images_bytes)} bytes)")

    r = requests.put(images_url, data=images_bytes, headers={"Content-Type": "application/zip"})
    assert r.status_code in (200, 201), f"Images upload failed: {r.status_code} {r.text[:200]}"
    print("[OK] Uploaded images.zip to GCS")

    # --- Upload masks.zip ---
    if args.masks and args.masks.exists():
        masks_bytes = args.masks.read_bytes()
        print(f"     Using real masks: {args.masks} ({len(masks_bytes)} bytes)")
    else:
        masks_bytes = make_dummy_zip("masks/test001.png")
        print(f"     Using dummy masks.zip ({len(masks_bytes)} bytes)")

    r = requests.put(masks_url, data=masks_bytes, headers={"Content-Type": "application/zip"})
    assert r.status_code in (200, 201), f"Masks upload failed: {r.status_code} {r.text[:200]}"
    print("[OK] Uploaded masks.zip to GCS")

    # --- Create eval job ---
    r = requests.post(f"{base}/jobs/eval", json={
        "model_id": "yolo_masking",
        "dataset_id": dataset_id,
    }, headers=headers)
    assert r.status_code == 201, f"Create job failed: {r.status_code} {r.text}"
    job = r.json()
    job_id = job["id"]
    print(f"[OK] Created eval job: {job_id} (status={job['status']})")

    # --- Run eval ---
    r = requests.post(f"{base}/jobs/{job_id}/run-eval", headers=headers)
    assert r.status_code == 200, f"Run eval failed: {r.status_code} {r.text}"
    print(f"[OK] Eval started (status={r.json()['status']})")

    # --- Poll until done/error ---
    print("     Polling for completion...")
    for i in range(60):
        time.sleep(2)
        r = requests.get(f"{base}/jobs/{job_id}/results", headers=headers)
        assert r.status_code == 200
        result = r.json()
        if result["status"] == "done":
            print(f"[OK] Job completed in ~{(i+1)*2}s")
            print(f"     mean_iou={result['mean_iou']}")
            print(f"     dice_score={result['dice_score']}")
            print(f"     pixel_accuracy={result['pixel_accuracy']}")
            print(f"     predictions={len(result.get('prediction_urls', []))} images")
            break
        elif result["status"] == "error":
            print(f"[ERR] Job failed: check /jobs/{job_id}/results for error_message")
            # Fetch the full job for error message
            r2 = requests.get(f"{base}/jobs", headers=headers)
            for j in r2.json():
                if j["id"] == job_id:
                    print(f"     error_message: {j.get('error_message', 'N/A')}")
            break
        else:
            if i % 5 == 0:
                print(f"     ... still {result['status']} ({(i+1)*2}s)")
    else:
        print("[TIMEOUT] Job did not complete within 120s")

    # --- List jobs ---
    r = requests.get(f"{base}/jobs", headers=headers)
    assert r.status_code == 200
    jobs = r.json()
    print(f"[OK] User has {len(jobs)} job(s)")

    # --- Logout ---
    r = requests.post(f"{base}/auth/logout", headers=headers)
    assert r.status_code in (200, 204)
    print("[OK] Logged out")

    print("\n=== E2E test complete ===")


if __name__ == "__main__":
    main()
