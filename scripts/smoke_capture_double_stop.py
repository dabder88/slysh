"""Smoke: double live stop is safe (A8 / plan-fix §3.1)."""
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
    print(f"smoke_capture_double_stop: FAIL: {msg}", file=sys.stderr)
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

    home = Path(tempfile.mkdtemp(prefix="slysh-double-stop-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    api_mod._list_input_mics = lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    api_mod.sd.InputStream = _FakeStream
    api_mod._handle_live_chunk = lambda *a, **k: None

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)

    live = client.post("/api/live/start", json={})
    if live.status_code != 200:
        return _fail(f"live/start {live.status_code}")
    job_id = int(live.json()["id"])
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))

    first = client.post("/api/live/stop")
    second = client.post("/api/live/stop")
    if first.status_code != 200:
        return _fail(f"first stop {first.status_code}")
    if second.status_code != 200:
        return _fail(f"second stop {second.status_code}")

    threads = getattr(app.state, "capture_finalize_threads", {}) or {}
    fin = threads.get(job_id)
    if fin is not None:
        fin.join(timeout=5.0)

    deadline = time.monotonic() + 5.0
    status = ""
    while time.monotonic() < deadline:
        status = (db.get_job(job_id) or {}).get("status") or ""
        if status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        ):
            break
        time.sleep(0.02)
    if status not in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
        return _fail(f"terminal status {status!r}")

    print("smoke_capture_double_stop: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
