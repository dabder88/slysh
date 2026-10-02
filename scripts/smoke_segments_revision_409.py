"""Smoke: PATCH segments with stale expected_revision returns 409 (B1)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_segments_revision_409: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus, Segment

    home = Path(tempfile.mkdtemp(prefix="slysh-rev-409-"))
    db = Database(home / "app.db")
    job_id = db.create_job(JobKind.FILE, str(home / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "one")])
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    ok = client.patch(
        f"/api/jobs/{job_id}/segments",
        json={"transcript": "[00:00:00] one\n", "expected_revision": 1},
    )
    if ok.status_code != 200:
        return _fail(f"first save {ok.status_code}")
    conflict = client.patch(
        f"/api/jobs/{job_id}/segments",
        json={"transcript": "[00:00:00] stale\n", "expected_revision": 1},
    )
    if conflict.status_code != 409:
        return _fail(f"expected 409, got {conflict.status_code}")
    print("smoke_segments_revision_409: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
