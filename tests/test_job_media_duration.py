from slysh.db import Database
from slysh.job_media_duration import job_media_duration_s, refresh_media_duration
from slysh.job_time import job_duration_s
from slysh.models import JobKind, Segment


def test_job_duration_s_is_processing_wall_clock():
    assert job_duration_s(
        {
            "started_at": "2026-08-16T10:00:00+00:00",
            "finished_at": "2026-08-16T10:00:30+00:00",
            "status": "completed",
        }
    ) == 30.0


def test_media_duration_from_segments_not_processing_time():
    job = {
        "id": 1,
        "kind": JobKind.FILE.value,
        "source_path": "",
        "started_at": "2026-08-16T10:00:00+00:00",
        "finished_at": "2026-08-16T10:00:30+00:00",
        "status": "completed",
    }
    segments = [Segment(0, 120_000, "text")]
    assert job_media_duration_s(job, segments=segments) == 120.0


def test_media_duration_from_range():
    job = {
        "id": 1,
        "kind": JobKind.FILE.value,
        "range_start_ms": 10_000,
        "range_end_ms": 70_000,
    }
    assert job_media_duration_s(job) == 60.0


def test_media_duration_youtube_metadata():
    job = {
        "id": 1,
        "kind": JobKind.YOUTUBE.value,
        "youtube": {"duration_s": 95.5},
    }
    assert job_media_duration_s(job) == 95.5


def test_refresh_media_duration_persists(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "x.wav"))
    db.replace_segments(job_id, [Segment(0, 45_000, "a")])
    refresh_media_duration(db, job_id)
    stored = db.get_job(job_id)
    assert stored is not None
    assert stored["media_duration_s"] == 45.0


def test_segment_max_end_ms_on_list_jobs(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "x.wav"))
    db.replace_segments(job_id, [Segment(0, 33_000, "a")])
    jobs = db.list_jobs()
    assert jobs[0]["segment_max_end_ms"] == 33_000
    assert job_media_duration_s(jobs[0]) == 33.0
