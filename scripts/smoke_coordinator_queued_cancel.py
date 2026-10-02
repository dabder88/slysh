"""Smoke: cancel QUEUED job pumps ASR queue (wave C)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-coord-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"

    pumped: list[str] = []
    api_mod._pump_asr_queues = lambda app, db: pumped.append("pump")

    db = Database(home / "app.db")
    job_id = db.create_job(JobKind.FILE, str(home / "x.wav"))
    db.begin_transcription(job_id)
    assert (db.get_job(job_id) or {}).get("status") == JobStatus.QUEUED.value

    client = TestClient(create_ui_app(db=db, engine=None, auto_start_engine=False))
    resp = client.post(f"/api/jobs/{job_id}/cancel")
    if resp.status_code != 200:
        print(f"smoke_coordinator_queued_cancel: FAIL cancel {resp.status_code}", file=sys.stderr)
        return 1
    if not pumped:
        print("smoke_coordinator_queued_cancel: FAIL pump not called", file=sys.stderr)
        return 1
    if (db.get_job(job_id) or {}).get("status") != JobStatus.CANCELLED.value:
        print("smoke_coordinator_queued_cancel: FAIL status", file=sys.stderr)
        return 1

    print("smoke_coordinator_queued_cancel: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
