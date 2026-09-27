from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment


def test_job_segments_and_speaker_rename(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\a.wav")
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет", speaker="SPEAKER_00")])
    db.upsert_speaker(job_id, "SPEAKER_00", "Иван")
    db.apply_speaker_names(job_id)
    segs = db.list_segments(job_id)
    assert segs[0].speaker == "Иван"
    jobs = db.list_jobs()
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["source_path"].endswith("a.wav")
    assert db.delete_job(job_id) is True
    assert db.get_job(job_id) is None
    assert db.list_segments(job_id) == []
    assert db.delete_job(job_id) is False


def test_job_speaker_stats_from_segments(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\a.wav")
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    job = db.get_job(job_id)
    assert job["has_speakers"] is False
    assert job["speaker_count"] == 0
    db.replace_segments(
        job_id,
        [
            Segment(0, 1000, "привет", speaker="SPEAKER_00"),
            Segment(1200, 2000, "алло", speaker="SPEAKER_01"),
            Segment(2200, 3000, "ещё", speaker="SPEAKER_00"),
        ],
    )
    job = db.get_job(job_id)
    assert job["has_speakers"] is True
    assert job["speaker_count"] == 2
    listed = db.list_jobs()
    assert listed[0]["has_speakers"] is True
    assert listed[0]["speaker_count"] == 2


def test_append_segments_preserves_order(tmp_path):
    db = Database(tmp_path / "app.db")
    job_a = db.create_job(JobKind.FILE, r"C:\a.wav")
    job_b = db.create_job(JobKind.FILE, r"C:\b.wav")
    db.append_segments(job_a, [Segment(0, 500, "one")])
    db.append_segments(job_a, [Segment(500, 1000, "two")])
    db.append_segments(job_b, [Segment(0, 200, "other")])
    segs_a = db.list_segments(job_a)
    assert [s.text for s in segs_a] == ["one", "two"]
    assert len(db.list_segments(job_b)) == 1
    db.replace_segments(job_a, [])
    assert db.list_segments(job_a) == []


def test_job_archive_flag(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\a.wav")
    job = db.get_job(job_id)
    assert job["archived"] == 0
    assert db.set_job_archived(job_id, True) is True
    assert db.get_job(job_id)["archived"] == 1
    assert db.set_job_archived(job_id, False) is True
    assert db.get_job(job_id)["archived"] == 0
