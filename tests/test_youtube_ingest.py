import pytest

from slysh.youtube_ingest import (
    YoutubeIngestError,
    extract_video_id,
    normalize_youtube_url,
)
from slysh.youtube_ytdlp import _pick_vtt_file


def test_extract_video_id_watch():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_short():
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_shorts():
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_normalize_youtube_url():
    url, video_id = normalize_youtube_url("youtu.be/dQw4w9WgXcQ")
    assert video_id == "dQw4w9WgXcQ"
    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_youtube_url_invalid():
    with pytest.raises(YoutubeIngestError):
        normalize_youtube_url("https://example.com/video")


def test_pick_vtt_prefers_ru(tmp_path):
    ru = tmp_path / "video.ru.vtt"
    en = tmp_path / "video.en.vtt"
    ru.write_text("WEBVTT\n", encoding="utf-8")
    en.write_text("WEBVTT\n", encoding="utf-8")
    picked = _pick_vtt_file([ru, en], "ru")
    assert picked == ru


def test_run_youtube_job_reports_increasing_progress(tmp_path, monkeypatch):
    from slysh.db import Database
    from slysh.models import JobKind, Segment
    from slysh.youtube_ingest import YoutubeTranscriptResult, run_youtube_job

    db = Database(tmp_path / "app.db")
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    job_id = db.create_job(JobKind.YOUTUBE, url)
    progress_values: list[float] = []
    original_set = db.set_progress

    def track_progress(jid: int, value: float) -> None:
        progress_values.append(value)
        original_set(jid, value)

    monkeypatch.setattr(db, "set_progress", track_progress)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript",
        lambda raw_url, method, language="ru": YoutubeTranscriptResult(
            title="Test",
            channel="Ch",
            channel_url="",
            upload_date="2024-01-01",
            video_id="dQw4w9WgXcQ",
            url=url,
            segments=[Segment(0, 500, "hello")],
        ),
    )

    run_youtube_job(db, job_id, url, "apify", "ru")

    assert len(progress_values) >= 3
    assert progress_values[0] <= progress_values[-1]
    assert progress_values[-1] == 1.0
    assert max(progress_values) > 0.15
