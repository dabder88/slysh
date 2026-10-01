"""Smoke: batch runner end-to-end — API create/items/start, mock ASR, real export (wave A5)."""
from __future__ import annotations

import sys
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_batch_export_runner_e2e: FAIL: {msg}", file=sys.stderr)
    return 1


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 400)


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh import api as api_mod
    from slysh.api import create_ui_app
    from slysh.batch_runner import get_runner
    from slysh.db import Database
    from slysh.models import BatchStatus, JobStatus, Segment

    home = Path(tempfile.mkdtemp(prefix="slysh-batch-export-e2e-"))
    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None)

    export_dir = home / "exports"
    export_dir.mkdir()
    wav_a = home / "folder_a" / "same.wav"
    wav_b = home / "folder_b" / "same.wav"
    _tiny_wav(wav_a)
    _tiny_wav(wav_b)
    path_a = str(wav_a.resolve())
    path_b = str(wav_b.resolve())
    segment_text = {path_a: "alpha", path_b: "beta"}

    def mock_file_asr(_app, _db, job_id: int, source_path: str) -> None:
        key = str(Path(source_path).resolve())
        text = segment_text.get(key, "?")
        _db.replace_segments(job_id, [Segment(0, 100, text)])
        _db.set_status(job_id, JobStatus.COMPLETED)

    rules = {
        "export": True,
        "export_fmt": "txt",
        "export_dir_mode": "fixed",
        "export_dir": str(export_dir),
        "on_error": "continue",
        "skip_completed": False,
        "speakers": False,
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/batches",
            json={"name": "export-collision-e2e", "rules": rules},
        )
        if created.status_code != 200:
            return _fail(f"create batch: {created.status_code} {created.text}")
        batch_id = int(created.json()["id"])

        added = client.post(
            f"/api/batches/{batch_id}/items",
            json={"paths": [path_a, path_b], "recursive": False},
        )
        if added.status_code != 200:
            return _fail(f"add items: {added.status_code} {added.text}")
        if len(added.json().get("jobs") or []) != 2:
            return _fail(f"expected 2 jobs, got {added.json()}")

        with (
            patch.object(api_mod, "_require_asr_ready", lambda: None),
            patch.object(api_mod, "_run_file_asr_job", mock_file_asr),
        ):
            started = client.post(f"/api/batches/{batch_id}/start")
        if started.status_code != 200:
            return _fail(f"start batch: {started.status_code} {started.text}")

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        with get_runner(app).lock:
            if get_runner(app).batch_id is None:
                break
        time.sleep(0.05)
    else:
        return _fail("batch runner did not finish in time")

    batch = db.get_batch(batch_id) or {}
    if batch.get("status") != BatchStatus.COMPLETED.value:
        return _fail(f"batch status {batch.get('status')}, summary={get_runner(app).summary}")

    paths = sorted(export_dir.glob("*.txt"))
    if len(paths) != 2:
        return _fail(f"expected 2 export files, got {[p.name for p in paths]}")
    names = {p.name for p in paths}
    if names != {"same.txt", "same__folder_b.txt"}:
        return _fail(f"unexpected export names: {names}")
    bodies = {p.read_text(encoding="utf-8").strip() for p in paths}
    if bodies != {"alpha", "beta"}:
        return _fail(f"unexpected export bodies: {bodies}")

    jobs = db.list_batch_jobs(batch_id)
    export_paths = []
    for job in jobs:
        raw = job.get("last_export_paths") or job.get("last_export_path")
        if isinstance(raw, list):
            export_paths.extend(raw)
        elif raw:
            export_paths.append(str(raw))
    if len(export_paths) != 2:
        return _fail(f"expected last_export_paths on jobs, got {export_paths}")

    print(
        "smoke_batch_export_runner_e2e: OK",
        sorted(names),
        f"batch_id={batch_id}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
