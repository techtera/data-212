"""Clear all jobs, sessions, and audit_log from Firestore for a fresh start.
Keeps model_registry intact.

Usage:
    cd D:\\TERAFAC\\AGENTIC-UI\\backend
    venv\\Scripts\\python.exe clear_firestore.py
"""
from __future__ import annotations
import os, sys
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "firebase-service-account.json")

from src.db.firebase import db  # noqa: E402
from src.db.crud import query_docs, delete_doc  # noqa: E402

COLLECTIONS_TO_CLEAR = ["jobs", "sessions", "users", "audit_log"]

def main():
    print("Clearing Firestore collections...")
    for col in COLLECTIONS_TO_CLEAR:
        docs = query_docs(col, limit=500)
        count = 0
        for doc in docs:
            delete_doc(col, doc["id"])
            count += 1
        print(f"  {col}: deleted {count} docs")
    print("Done. Fresh start ready.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
