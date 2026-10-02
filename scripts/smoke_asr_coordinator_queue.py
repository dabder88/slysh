"""Smoke: two local file jobs run one-after-another via ASR coordinator (wave C.1)."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_asr_coordinator_queue: FAIL: {msg}", file=sys.stderr)
    return 1


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 400)


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-coord-q-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"

    db = Database(home / "app.db")
    wav_a = home / "a.wav"
    wav_b = home / "b.wav"
    _tiny_wav(wav_a)
    _tiny_wav(wav_b)
    j1 = db.create_job(JobKind.FILE, str(wav_a))
    j2 = db.create_job(JobKind.FILE, str(wav_b))

    order: list[int] = []
    active = {"id": None}
    lock = threading.Lock()

    def fake_run_engine(_db, _url, job_id: int, _path: str) -> None:
        with lock:
            if active["id"] is not None:
                raise RuntimeError(f"overlap: {active['id']} and {job_id}")
            active["id"] = job_id
            order.append(job_id)
        time.sleep(0.08)
        _db.set_status(job_id, JobStatus.COMPLETED)
        with lock:
            active["id"] = None

    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    app.state.engine_url = "http://127.0.0.1:9"

    with (
        patch.object(api_mod, "_run_engine_job", fake_run_engine),
        patch.object(api_mod, "_engine_status", lambda _app: "cpu"),
        patch.object(api_mod, "_selected_asr_preflight_error", lambda: None),
    ):
        client = TestClient(app)
        r1 = client.post(f"/api/jobs/{j1}/start")
        r2 = client.post(f"/api/jobs/{j2}/start")
        if r1.status_code != 200 or r2.status_code != 200:
            return _fail(f"start HTTP {r1.status_code} {r2.status_code}")

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if order == [j1, j2]:
                j1s = (db.get_job(j1) or {}).get("status")
                j2s = (db.get_job(j2) or {}).get("status")
                if j1s == JobStatus.COMPLETED.value and j2s == JobStatus.COMPLETED.value:
                    print("smoke_asr_coordinator_queue: OK")
                    return 0
            time.sleep(0.05)

    return _fail(f"timeout order={order} statuses={(db.get_job(j1) or {}).get('status')}, {(db.get_job(j2) or {}).get('status')}")


if __name__ == "__main__":
    raise SystemExit(main())
