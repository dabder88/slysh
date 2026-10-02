"""Smoke: live stop sets job status finalizing until ASR finalize completes (A8)."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_capture_job_finalizing_status: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import create_ui_app
    from slysh.chunking import SAMPLE_RATE
    from slysh.db import Database
    from slysh.models import JobStatus

    class _FakeStream:
        def __init__(self, **kwargs):
            pass

        def start(self):
            return None

        def stop(self):
            return None

        def close(self):
            return None

    def slow_handle(app, db, pcm, *, capture_state=None):
        time.sleep(0.35)

    home = Path(tempfile.mkdtemp(prefix="slysh-smoke-finalizing-status-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    api_mod._list_input_mics = lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    api_mod.sd.InputStream = _FakeStream
    api_mod._handle_live_chunk = slow_handle

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)

    live = client.post("/api/live/start", json={})
    if live.status_code != 200:
        return _fail(f"live/start {live.status_code}")
    job_id = int(live.json()["id"])
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    t0 = time.monotonic()
    stop = client.post("/api/live/stop")
    if stop.status_code != 200:
        return _fail(f"live/stop {stop.status_code}")
    if time.monotonic() - t0 > 0.35:
        return _fail("live/stop blocked on slow ASR")

    job = db.get_job(job_id) or {}
    if job.get("status") != JobStatus.FINALIZING.value:
        return _fail(f"expected finalizing, got {job.get('status')}")

    threads = getattr(app.state, "capture_finalize_threads", {}) or {}
    thread = threads.get(job_id)
    if thread is not None:
        thread.join(timeout=5.0)
    job = db.get_job(job_id) or {}
    if job.get("status") != JobStatus.COMPLETED.value:
        return _fail(f"expected completed after finalize, got {job.get('status')}")

    print("smoke_capture_job_finalizing_status: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
