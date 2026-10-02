"""Smoke: live pause/resume/stop serialization (B4.2–B4.3)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import create_ui_app
    from slysh.chunking import LIVE_CHUNK_SAMPLES, SAMPLE_RATE
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

    home = Path(tempfile.mkdtemp(prefix="slysh-pause-resume-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    api_mod._list_input_mics = lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    api_mod.sd.InputStream = _FakeStream
    handled: list[int] = []
    api_mod._handle_live_chunk = lambda app, db, pcm, **kw: handled.append(int(len(pcm)))

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)

    start = client.post("/api/live/start", json={})
    if start.status_code != 200:
        print("smoke_capture_pause_resume: FAIL start", file=sys.stderr)
        return 1
    job_id = int(start.json()["id"])
    session = app.state.live["session"]
    total = 0
    for _ in range(4):
        n = SAMPLE_RATE // 2
        session.push(np.zeros(n, np.float32))
        total += n
        if client.post("/api/live/pause").status_code != 200:
            print("smoke_capture_pause_resume: FAIL pause", file=sys.stderr)
            return 1
        if client.post("/api/live/resume").status_code != 200:
            print("smoke_capture_pause_resume: FAIL resume", file=sys.stderr)
            return 1
    session.push(np.zeros(LIVE_CHUNK_SAMPLES, np.float32))
    total += LIVE_CHUNK_SAMPLES
    if client.post("/api/live/stop").status_code != 200:
        print("smoke_capture_pause_resume: FAIL stop", file=sys.stderr)
        return 1
    fin = (getattr(app.state, "capture_finalize_threads", None) or {}).get(job_id)
    if fin is not None:
        fin.join(timeout=5.0)
    if sum(handled) != total:
        print(
            f"smoke_capture_pause_resume: FAIL samples {sum(handled)} != {total}",
            file=sys.stderr,
        )
        return 1

    print("smoke_capture_pause_resume: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
