"""Smoke: cancel RUNNING local job releases slot and pumps queued job (wave C.3)."""
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
    print(f"smoke_coordinator_cancel_running_pump: FAIL: {msg}", file=sys.stderr)
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
    from slysh.asr_coordinator import job_run_active, job_run_id
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-cancel-run-"))
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

    engine_cancels: list[str] = []
    engine_calls: list[int] = []

    def fake_run_engine(_db, url: str, job_id: int, _path: str) -> None:
        engine_calls.append(job_id)
        run_id = job_run_id(_db, job_id)
        _db.set_status(job_id, JobStatus.RUNNING)
        if job_id == j1:
            while job_run_active(_db, job_id, run_id):
                time.sleep(0.03)
            return
        _db.set_status(job_id, JobStatus.COMPLETED)

    def fake_engine_cancel(url: str) -> None:
        engine_cancels.append(url)

    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    app.state.engine_url = "http://127.0.0.1:9"

    with (
        patch.object(api_mod, "_run_engine_job", fake_run_engine),
        patch.object(api_mod, "_engine_status", lambda _app: "cpu"),
        patch.object(api_mod, "_selected_asr_preflight_error", lambda: None),
        patch.object(api_mod, "engine_cancel", fake_engine_cancel),
    ):
        client = TestClient(app)
        if client.post(f"/api/jobs/{j1}/start").status_code != 200:
            return _fail("start j1")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (db.get_job(j1) or {}).get("status") == JobStatus.RUNNING.value:
                break
            time.sleep(0.03)
        else:
            return _fail("j1 never reached RUNNING")

        if client.post(f"/api/jobs/{j2}/start").status_code != 200:
            return _fail("start j2")
        if (db.get_job(j2) or {}).get("status") != JobStatus.QUEUED.value:
            return _fail(f"j2 expected QUEUED, got {(db.get_job(j2) or {}).get('status')}")

        if client.post(f"/api/jobs/{j1}/cancel").status_code != 200:
            return _fail("cancel j1")
        if not engine_cancels:
            return _fail("engine_cancel was not called")

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            j1s = (db.get_job(j1) or {}).get("status")
            j2s = (db.get_job(j2) or {}).get("status")
            if j1s == JobStatus.CANCELLED.value and j2s == JobStatus.COMPLETED.value:
                if engine_calls != [j1, j2]:
                    return _fail(f"engine call order {engine_calls}")
                print("smoke_coordinator_cancel_running_pump: OK")
                return 0
            time.sleep(0.05)

    return _fail(
        f"timeout j1={(db.get_job(j1) or {}).get('status')} j2={(db.get_job(j2) or {}).get('status')}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
