"""Wave A5: fixed-dir batch export must not overwrite same stem from different folders."""
from __future__ import annotations

from pathlib import Path

from slysh.batch_runner import _export_batch_job
from slysh.db import Database
from slysh.export import unique_export_path
from slysh.models import JobKind, Segment


def test_unique_export_path_scoped_per_directory(tmp_path):
    used: set[str] = set()
    d1 = tmp_path / "out1"
    d2 = tmp_path / "out2"
    p1 = unique_export_path(d1, "clip", "srt", used)
    p2 = unique_export_path(d2, "clip", "srt", used)
    assert p1.name == "clip.srt"
    assert p2.name == "clip.srt"
    p3 = unique_export_path(d1, "clip", "srt", used)
    assert p3.name == "clip_2.srt"


def test_batch_export_same_stem_different_parents(tmp_path):
    db = Database(tmp_path / "app.db")
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    a = tmp_path / "folder_a" / "same.wav"
    b = tmp_path / "folder_b" / "same.wav"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"x")
    b.write_bytes(b"y")

    job_a = db.create_job(JobKind.FILE, str(a))
    job_b = db.create_job(JobKind.FILE, str(b))
    db.replace_segments(job_a, [Segment(0, 100, "A")])
    db.replace_segments(job_b, [Segment(0, 100, "B")])

    rules = {
        "export": True,
        "export_fmt": "txt",
        "export_dir_mode": "fixed",
        "export_dir": str(export_dir),
    }
    used: set[str] = set()
    _export_batch_job(db, job_a, db.get_job(job_a) or {}, rules, used_names=used)
    _export_batch_job(db, job_b, db.get_job(job_b) or {}, rules, used_names=used)

    paths = sorted(export_dir.glob("*.txt"))
    assert len(paths) == 2
    names = {p.name for p in paths}
    assert "same.txt" in names
    assert "same__folder_b.txt" in names
    contents = {p.read_text(encoding="utf-8").strip() for p in paths}
    assert "A" in contents and "B" in contents
