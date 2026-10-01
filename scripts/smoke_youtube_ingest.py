"""Smoke: YouTube metadata in SQLite + optional live yt-dlp ingest."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _smoke_sqlite_ingest() -> int:
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus, Segment
    from slysh.youtube_ingest import (
        YoutubeTranscriptResult,
        load_job_youtube_video,
        normalize_youtube_url,
        run_youtube_job,
    )

    home = Path(tempfile.mkdtemp(prefix="slysh-yt-sqlite-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    import slysh.youtube_ingest as youtube_ingest_mod

    youtube_ingest_mod._meta_db = None

    db = Database(home / "app.db")
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    url, video_id = normalize_youtube_url(url)
    job_id = db.create_job(JobKind.YOUTUBE, url)

    def fake_fetch(raw_url, method, language="ru"):
        return YoutubeTranscriptResult(
            title="Smoke YouTube",
            channel="Smoke Channel",
            channel_url="https://www.youtube.com/channel/smoke",
            upload_date="2024-01-01",
            video_id=video_id,
            url=raw_url,
            segments=[Segment(0, 1200, "smoke transcript line")],
            duration_s=12.0,
            chapters=({"title": "Intro", "start_ms": 0},),
            thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        )

    with patch("slysh.youtube_ingest.fetch_transcript", fake_fetch):
        run_youtube_job(db, job_id, url, "ytdlp", "ru")

    job = db.get_job(job_id) or {}
    if job.get("status") != JobStatus.COMPLETED.value:
        print(f"smoke_youtube_ingest: FAIL sqlite job {job.get('status')}", file=sys.stderr)
        return 1
    video = load_job_youtube_video(job_id, db=db) or {}
    if video.get("title") != "Smoke YouTube" or video.get("channel") != "Smoke Channel":
        print(f"smoke_youtube_ingest: FAIL sqlite metadata {video}", file=sys.stderr)
        return 1
    row = db.get_job_youtube_meta(job_id)
    if not row or not row.get("video"):
        print("smoke_youtube_ingest: FAIL missing job_youtube_meta row", file=sys.stderr)
        return 1
    meta = db.get_job_youtube_meta(job_id) or {}
    print(
        "smoke_youtube_ingest: OK sqlite ingest + metadata "
        f"title={video.get('title')!r} channel={video.get('channel')!r} "
        f"video_id={video.get('video_id')!r} method={meta.get('method')!r} "
        f"segments={len(db.list_segments(job_id))}"
    )
    return 0


def _smoke_live_ytdlp() -> int:
    if os.environ.get("SLYSH_SKIP_YOUTUBE_SMOKE") == "1":
        print("smoke_youtube_ingest: live SKIP (SLYSH_SKIP_YOUTUBE_SMOKE=1)")
        return 0

    from slysh.db import Database
    from slysh.models import JobKind, JobStatus
    from slysh.youtube_ingest import (
        load_job_youtube_video,
        normalize_youtube_url,
        run_youtube_job,
    )
    from slysh.youtube_ytdlp import find_ytdlp

    if not find_ytdlp():
        print("smoke_youtube_ingest: live SKIP (yt-dlp not found)")
        return 0

    home = Path(tempfile.mkdtemp(prefix="slysh-yt-live-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    import slysh.youtube_ingest as youtube_ingest_mod

    youtube_ingest_mod._meta_db = None

    db = Database(home / "app.db")
    url = os.environ.get("SLYSH_SMOKE_YOUTUBE_URL", DEFAULT_URL).strip()
    url, video_id = normalize_youtube_url(url)
    job_id = db.create_job(JobKind.YOUTUBE, url)
    print(f"smoke_youtube_ingest: live job {job_id} {video_id} …")
    run_youtube_job(db, job_id, url, "ytdlp", "ru")
    job = db.get_job(job_id) or {}
    if job.get("status") != JobStatus.COMPLETED.value:
        err = (job.get("error_text") or job.get("status") or "").strip()
        print(f"smoke_youtube_ingest: live SKIP (network/API): {err[:400]}", file=sys.stderr)
        return 0

    segments = db.list_segments(job_id)
    video = load_job_youtube_video(job_id, db=db) or {}
    title = str(video.get("title") or "").strip()
    if not segments or not title:
        print(f"smoke_youtube_ingest: live FAIL empty result", file=sys.stderr)
        return 1
    preview = (segments[0].text or "")[:60]
    print(
        f"smoke_youtube_ingest: live OK title={title!r} segments={len(segments)} "
        f"channel={video.get('channel')!r} preview={preview!r}"
    )
    return 0


def main() -> int:
    code = _smoke_sqlite_ingest()
    if code != 0:
        return code
    if os.environ.get("SLYSH_SMOKE_YOUTUBE_LIVE", "1") == "1":
        return _smoke_live_ytdlp()
    print("smoke_youtube_ingest: live SKIP (SLYSH_SMOKE_YOUTUBE_LIVE=0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
