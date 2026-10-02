"""Smoke: speaker display name can change twice; segment keys stay stable (A6)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_speaker_rename_twice: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus, Segment

    home = Path(tempfile.mkdtemp(prefix="slysh-speaker-rename-"))
    db = Database(home / "app.db")
    job_id = db.create_job(JobKind.FILE, str(home / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет", speaker="SPEAKER_00")])

    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)

    for name in ("Alice", "Bob"):
        r = client.put(f"/api/jobs/{job_id}/speakers", json={"SPEAKER_00": name})
        if r.status_code != 200:
            return _fail(f"rename {name}: {r.status_code} {r.text}")
        if r.json().get("speaker_names", {}).get("SPEAKER_00") != name:
            return _fail(f"speaker_names mismatch for {name}")

    job = client.get(f"/api/jobs/{job_id}").json()
    seg = (job.get("segments") or [{}])[0]
    if seg.get("speaker_key") != "SPEAKER_00":
        return _fail(f"speaker_key={seg.get('speaker_key')}")
    if seg.get("speaker") != "Bob":
        return _fail(f"display speaker={seg.get('speaker')}")
    if db.list_segments(job_id)[0].speaker != "SPEAKER_00":
        return _fail("DB segment key mutated")

    print("smoke_speaker_rename_twice: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
