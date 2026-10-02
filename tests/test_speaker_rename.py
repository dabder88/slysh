"""Wave A6: speaker_key stable in DB; display names only in speakers table."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.api import _display_segments, create_ui_app
from slysh.db import Database
from slysh.export import write_job_export
from slysh.models import JobKind, Segment


def test_rename_speakers_twice_keeps_segment_keys(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.replace_segments(
        job_id,
        [Segment(0, 100, "hello", speaker="SPEAKER_00")],
    )

    client = TestClient(app)
    for name in ("Алиса", "Боб", "Вера"):
        r = client.put(
            f"/api/jobs/{job_id}/speakers",
            json={"SPEAKER_00": name},
        )
        assert r.status_code == 200
        assert r.json()["speaker_names"]["SPEAKER_00"] == name

    got = client.get(f"/api/jobs/{job_id}").json()
    assert got["segments"][0]["speaker_key"] == "SPEAKER_00"
    assert got["segments"][0]["speaker"] == "Вера"
    assert db.list_segments(job_id)[0].speaker == "SPEAKER_00"

    out = tmp_path / "out.txt"
    job = db.get_job(job_id) or {}
    segs = _display_segments(db, job_id, db.list_segments(job_id))
    write_job_export(out, segs, "txt", job=job)
    text = out.read_text(encoding="utf-8")
    assert "Вера:" in text or text.startswith("Вера")

