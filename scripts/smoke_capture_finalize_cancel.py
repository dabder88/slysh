"""Smoke: cancel job during live capture finalize calls engine_cancel (wave C)."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_capture_finalize_cancel: FAIL: {msg}", file=sys.stderr)
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

    held = threading.Event()
    released = threading.Event()
    cancels: list[str] = []

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=3.0)

    home = Path(tempfile.mkdtemp(prefix="slysh-smoke-finalize-cancel-"))
    import os

    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)

    api_mod._list_input_mics = lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    api_mod.sd.InputStream = _FakeStream
    api_mod._handle_live_chunk = slow_handle
    api_mod._capture_finalize_uses_local_engine = lambda app: True
    api_mod._require_asr_ready = lambda: None
    api_mod.engine_cancel = lambda url: cancels.append(url)

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    app.state.engine_url = "http://engine.smoke.test"
    client = TestClient(app)

    started = client.post("/api/live/start", json={})
    if started.status_code != 200:
        return _fail(f"live/start {started.status_code}: {started.text}")
    job_id = started.json()["id"]
    session = app.state.live.get("session")
    if session is None:
        return _fail("no live session after start")
    session.push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    if not held.wait(timeout=3.0):
        return _fail("finalize did not start (slow_handle not called)")
    cancel = client.post(f"/api/jobs/{job_id}/cancel")
    if cancel.status_code != 200:
        return _fail(f"cancel {cancel.status_code}")
    if cancels != ["http://engine.smoke.test"]:
        return _fail(f"engine_cancel calls={cancels!r}")
    if (db.get_job(job_id) or {}).get("status") != JobStatus.CANCELLED.value:
        return _fail("job not cancelled")
    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {}) or {}
    t = threads.get(job_id)
    if t is not None:
        t.join(timeout=5.0)
    print("smoke_capture_finalize_cancel: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
