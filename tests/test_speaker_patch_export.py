"""A6: speaker keys in DB; display names in export; save maps labels back to keys."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import _write_job_export_file, create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment


def test_patch_transcript_maps_display_name_to_speaker_key(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "звонок.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет", speaker="SPEAKER_00")])
    db.upsert_speaker(job_id, "SPEAKER_00", "Иван")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    transcript = "[00:00:00] Иван: привет\n"
    r = client.patch(
        f"/api/jobs/{job_id}/segments",
        json={"transcript": transcript, "expected_revision": 1},
    )
    assert r.status_code == 200
    assert db.list_segments(job_id)[0].speaker == "SPEAKER_00"


def test_export_uses_display_speaker_unicode(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "встреча.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(
        job_id,
        [Segment(0, 1500, "текст", speaker="SPEAKER_00")],
    )
    db.upsert_speaker(job_id, "SPEAKER_00", "Спикер «А»")
    job = db.get_job(job_id) or {}
    out = tmp_path / "out.txt"
    _write_job_export_file(db, job, out, "txt")
    body = out.read_text(encoding="utf-8")
    assert "Спикер «А»: текст" in body
    assert "SPEAKER_00" not in body
