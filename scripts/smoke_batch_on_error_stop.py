"""Smoke: file batch on_error=stop pauses after first failure (wave A4)."""
from __future__ import annotations

import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_batch_on_error_stop: FAIL: {msg}", file=sys.stderr)
    return 1


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 400)


def main() -> int:
    from slysh.api import create_ui_app
    from slysh.batch_runner import get_runner, start_batch
    from slysh.db import Database
    from slysh.models import BatchStatus, JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-batch-stop-"))
    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None)
    ok = home / "ok.wav"
    _tiny_wav(ok)
    batch_id = db.create_batch("smoke", {"on_error": "stop", "skip_completed": False})
    db.create_job(JobKind.FILE, str(ok), batch_id=batch_id)
    db.create_job(JobKind.FILE, str(home / "nope.wav"), batch_id=batch_id)

    seen: list[int] = []

    def run_job(_app, _db, job_id, _path):
        seen.append(job_id)
        _db.set_status(job_id, JobStatus.COMPLETED)

    start_batch(
        app,
        db,
        batch_id,
        run_file_job=run_job,
        ensure_engine=lambda _a: "http://127.0.0.1:9",
        run_engine_job=lambda *_a: None,
        engine_cancel=lambda _u: None,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with get_runner(app).lock:
            if get_runner(app).batch_id is None:
                break
        time.sleep(0.05)

    if db.get_batch(batch_id)["status"] != BatchStatus.PAUSED.value:
        return _fail(f"batch status {db.get_batch(batch_id)['status']}")
    if len(seen) != 1:
        return _fail(f"expected 1 job run, got {len(seen)}")
    summary = get_runner(app).summary or {}
    if summary.get("pause_reason") != "on_error_stop":
        return _fail(f"summary {summary}")
    print("smoke_batch_on_error_stop: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
