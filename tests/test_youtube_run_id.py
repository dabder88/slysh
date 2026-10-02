"""YouTube ingest respects job run_id (wave C)."""
from __future__ import annotations

import threading

from slysh.asr_coordinator import job_run_active, job_run_id
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.youtube_ingest import YoutubeTranscriptResult, run_youtube_job


def test_youtube_job_skips_write_when_run_id_stale(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.YOUTUBE, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    db.begin_transcription(job_id)
    stale_run = job_run_id(db, job_id)

    reached_fetch = threading.Event()
    release_fetch = threading.Event()

    def slow_fetch(url, method, language="ru"):
        reached_fetch.set()
        release_fetch.wait(timeout=5.0)
        return YoutubeTranscriptResult(
            title="Stale",
            channel="C",
            channel_url="",
            upload_date="2024-01-01",
            video_id="dQw4w9WgXcQ",
            url=url,
            segments=[Segment(0, 1000, "should not land")],
        )

    monkeypatch.setattr("slysh.youtube_ingest.fetch_transcript", slow_fetch)

    worker = threading.Thread(
        target=run_youtube_job,
        args=(db, job_id, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "ytdlp", "ru"),
        daemon=True,
    )
    worker.start()
    assert reached_fetch.wait(timeout=5.0), "fetch should block before restart"
    db.begin_transcription(job_id)
    assert job_run_id(db, job_id) != stale_run
    assert not job_run_active(db, job_id, stale_run)
    release_fetch.set()
    worker.join(timeout=10.0)

    job = db.get_job(job_id) or {}
    assert job.get("status") != JobStatus.COMPLETED.value
    assert not db.list_segments(job_id)
