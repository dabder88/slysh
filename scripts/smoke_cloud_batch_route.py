"""Smoke: cloud_only + remote model batch job must not call local engine (wave A3)."""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_cloud_batch_route: FAIL: {msg}", file=sys.stderr)
    return 1


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 800)


def main() -> int:
    from slysh import api as api_mod
    from slysh.api import _run_file_asr_job, create_ui_app
    from slysh.catalog import ModelItem
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus

    home = Path(tempfile.mkdtemp(prefix="slysh-cloud-batch-"))
    db = Database(home / "app.db")
    wav = home / "x.wav"
    _tiny_wav(wav)
    job_id = db.create_job(JobKind.FILE, str(wav))
    app = create_ui_app(db=db, engine=None)

    remote = ModelItem(
        id="smoke-remote",
        label="Smoke remote",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )

    def fail_engine(*_a, **_k):
        raise RuntimeError("engine must not run")

    def complete(_app, _db, jid, _path, *, reset_segments=True, **_kwargs):
        _db.set_status(jid, JobStatus.COMPLETED)

    from unittest.mock import patch

    db.begin_transcription(job_id)
    try:
        with (
            patch.object(api_mod, "is_cloud_only", lambda: True),
            patch.object(api_mod, "_selected_model", lambda: remote),
            patch.object(api_mod, "_ensure_engine_url", fail_engine),
            patch.object(api_mod, "_run_remote_job", complete),
        ):
            _run_file_asr_job(app, db, job_id, str(wav))
    except Exception as exc:
        return _fail(str(exc))
    if db.get_job(job_id)["status"] != JobStatus.COMPLETED.value:
        return _fail(f"job status {db.get_job(job_id)['status']}")
    print("smoke_cloud_batch_route: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
