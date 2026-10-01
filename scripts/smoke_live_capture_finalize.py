"""Smoke: capture finalize respects ASR errors (wave A8)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_live_capture_finalize: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from slysh.api import _finalize_capture_job
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-live-finalize-"))
    db = Database(home / "app.db")
    job_id = db.create_job(JobKind.LIVE, str(home / "x.wav"))
    db.set_status(job_id, JobStatus.RUNNING)
    _finalize_capture_job(db, {"error": "mock asr failure"}, job_id)
    job = db.get_job(job_id) or {}
    if job.get("status") != JobStatus.FAILED.value:
        return _fail(f"status={job.get('status')}")
    print("smoke_live_capture_finalize: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
