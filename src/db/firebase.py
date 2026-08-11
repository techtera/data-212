from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env before reading any env vars — safe to call multiple times (idempotent).
load_dotenv()

logger = logging.getLogger(__name__)

# Module-level db reference — populated by init_firebase().
# Typed as Any here because google.cloud.firestore is not imported at module scope
# (it lives inside init_firebase to allow mocking in tests).
# Other modules import `db` from here; they must NOT import firebase_admin directly.
db: Any = None


def init_firebase() -> None:
    """Initialise the Firebase Admin SDK and expose the Firestore client as `db`.

    Rules:
    - Credential path is read exclusively from the GOOGLE_APPLICATION_CREDENTIALS
      environment variable, with a fallback of "firebase-service-account.json"
      relative to the repo root (two directories above this file).
    - If the resolved path does not exist, a RuntimeError is raised.
      The path itself is NOT included in the error message or any log output.
    - firebase_admin.get_app() is checked first to avoid double-initialisation.
    - No credential content is ever read, printed, or logged by this function.
    """
    import firebase_admin  # type: ignore[import-untyped]
    from firebase_admin import credentials, firestore  # type: ignore[import-untyped]

    global db

    # ── Resolve credential file path ──────────────────────────────────────────
    env_val = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if env_val:
        cred_path = Path(env_val)
    else:
        # Default: repo root (backend/../firebase-service-account.json)
        repo_root = Path(__file__).resolve().parent.parent.parent
        cred_path = repo_root / "firebase-service-account.json"

    if not cred_path.exists():
        raise RuntimeError(
            "Firebase credential file not found. "
            "Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to the "
            "path of your service-account JSON file."
        )

    # ── Initialise (once) ─────────────────────────────────────────────────────
    try:
        firebase_admin.get_app()
        logger.debug("Firebase app already initialised — skipping.")
    except ValueError:
        # No default app exists yet — initialise now.
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialised.")

    db = firestore.client()


# Auto-initialise when this module is first imported.
init_firebase()
