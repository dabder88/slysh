"""Smoke: GET /api/jobs/{id}/media rejects parent-segment paths (D.4)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind

    home = Path(tempfile.mkdtemp(prefix="slysh-media-"))
    secret = home / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    db = Database(home / "app.db")
    job_id = db.create_job(JobKind.FILE, str(home / ".." / "secret.txt"))
    client = TestClient(create_ui_app(db=db, engine=None))

    resp = client.get(f"/api/jobs/{job_id}/media")
    if resp.status_code != 404:
        print(f"smoke_job_media_traversal: FAIL expected 404 got {resp.status_code}", file=sys.stderr)
        return 1

    media = home / "ok.wav"
    media.write_bytes(b"RIFF")
    job_ok = db.create_job(JobKind.FILE, str(media))
    ok = client.get(f"/api/jobs/{job_ok}/media")
    if ok.status_code != 200:
        print(f"smoke_job_media_traversal: FAIL valid media {ok.status_code}", file=sys.stderr)
        return 1

    print("smoke_job_media_traversal: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
