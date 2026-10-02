"""Smoke: live/meeting start blocked with CAPTURE_FINALIZING_HINT during finalize."""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_capture_finalize_start_blocked: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    import os

    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import CAPTURE_FINALIZING_HINT, create_ui_app
    from slysh.chunking import SAMPLE_RATE
    from slysh.db import Database

    class _FakeStream:
        def __init__(self, **kwargs):
            pass

        def start(self):
            return None

        def stop(self):
            return None

        def close(self):
            return None

    class _FakeCapture:
        def __init__(self, **kwargs):
            pass

        def start(self):
            return None

        def stop(self):
            return None

    held = threading.Event()
    released = threading.Event()

    def slow_handle(app, db, pcm, *, capture_state=None):
        held.set()
        released.wait(timeout=3.0)

    home = Path(tempfile.mkdtemp(prefix="slysh-smoke-finalize-block-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    api_mod._list_input_mics = lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    api_mod.sd.InputStream = _FakeStream
    api_mod._handle_live_chunk = slow_handle
    api_mod._capture_finalize_uses_local_engine = lambda app: True
    api_mod._require_asr_ready = lambda: None
    api_mod.loopback_supported = lambda: True
    api_mod.list_output_devices = lambda: [{"id": 3, "name": "Speakers"}]
    api_mod.MeetingCapture = _FakeCapture

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)

    live = client.post("/api/live/start", json={})
    if live.status_code != 200:
        return _fail(f"live/start {live.status_code}")
    app.state.live["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/live/stop")
    if not held.wait(timeout=3.0):
        return _fail("live finalize did not start")
    blocked = client.post("/api/live/start", json={})
    if blocked.status_code != 400 or blocked.json().get("detail") != CAPTURE_FINALIZING_HINT:
        return _fail(f"live second start: {blocked.status_code} {blocked.text}")
    released.set()
    for t in list((getattr(app.state, "capture_finalize_threads", {}) or {}).values()):
        t.join(timeout=5.0)

    held.clear()
    released.clear()
    meet = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    if meet.status_code != 200:
        return _fail(f"meeting/start {meet.status_code}")
    job_id = meet.json()["id"]
    app.state.meeting["session"].push(np.zeros(SAMPLE_RATE, np.float32))
    client.post("/api/meeting/stop")
    if not held.wait(timeout=3.0):
        return _fail("meeting finalize did not start")
    blocked_m = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    if blocked_m.status_code != 400 or blocked_m.json().get("detail") != CAPTURE_FINALIZING_HINT:
        return _fail(f"meeting second start: {blocked_m.status_code} {blocked_m.text}")
    released.set()
    threads = getattr(app.state, "capture_finalize_threads", {}) or {}
    if threads.get(job_id):
        threads[job_id].join(timeout=5.0)

    print("smoke_capture_finalize_start_blocked: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
