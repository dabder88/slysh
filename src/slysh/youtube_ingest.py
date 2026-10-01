from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

from slysh.models import Segment
from slysh.paths import youtube_dir
from slysh.providers import apify_api_key
from slysh.vtt import merge_segments
from slysh.youtube_apify import YoutubeApifyError, fetch_transcript_apify
from slysh.youtube_cookies import browser_cookie3_available, cookies_present
from slysh.youtube_transcript_api import (
    YoutubeTranscriptApiError,
    fetch_transcript_api,
    transcript_api_available,
)
from slysh.youtube_ytdlp import (
    YoutubeYtdlpError,
    cookies_auth_mode,
    fetch_transcript_ytdlp,
    find_ytdlp,
    is_usable_audio_file,
)

YoutubeMethod = Literal["apify", "ytdlp"]

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_meta_db: object | None = None
_meta_db_lock = threading.Lock()


class YoutubeIngestError(Exception):
    """Raised when YouTube URL or transcript fetch is invalid."""


@dataclass(frozen=True)
class YoutubeTranscriptResult:
    title: str
    channel: str
    channel_url: str
    upload_date: str
    video_id: str
    url: str
    segments: list[Segment]
    duration_s: float | None = None
    chapters: tuple[dict, ...] = ()
    thumbnail_url: str = ""


def _duration_from_segments(segments: list[Segment]) -> float | None:
    if not segments:
        return None
    return max(segment.end_ms for segment in segments) / 1000.0


def youtube_video_meta(result: YoutubeTranscriptResult) -> dict:
    duration_s = result.duration_s
    if duration_s is None:
        duration_s = _duration_from_segments(result.segments)
    return {
        "video_id": result.video_id,
        "url": result.url,
        "title": result.title,
        "channel": result.channel,
        "channel_url": result.channel_url,
        "upload_date": result.upload_date,
        "duration_s": round(duration_s, 1) if duration_s is not None else None,
        "chapters": [dict(chapter) for chapter in result.chapters],
        "thumbnail_url": result.thumbnail_url,
    }


def _meta_database():
    global _meta_db
    with _meta_db_lock:
        if _meta_db is None:
            from slysh.db import Database
            from slysh.paths import db_path

            _meta_db = Database(db_path())
        return _meta_db


def _resolve_meta_db(db=None):
    return db if db is not None else _meta_database()


def load_job_youtube_video(job_id: int, *, db=None) -> dict | None:
    row = _resolve_meta_db(db).get_job_youtube_meta(job_id)
    if not row:
        return None
    video = row.get("video")
    return dict(video) if isinstance(video, dict) else None


def fallback_youtube_video_from_job(job: dict) -> dict:
    url = str(job.get("source_path") or "").strip()
    video_id = extract_video_id(url) or ""
    return {
        "video_id": video_id,
        "url": url,
        "title": str(job.get("source_title") or "").strip(),
        "channel": "",
        "channel_url": "",
        "upload_date": "",
        "duration_s": None,
        "chapters": [],
        "thumbnail_url": (
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""
        ),
    }


def attach_youtube_video(
    job: dict,
    segments: list | None = None,
    *,
    enrich: bool = False,
) -> None:
    if str(job.get("kind") or "") != "youtube":
        return
    from slysh.youtube_metadata import (
        enrich_video_payload,
        video_metadata_needs_enrichment,
    )

    job_id = int(job["id"])
    video = load_job_youtube_video(job_id) or fallback_youtube_video_from_job(job)
    if not video.get("chapters") and video.get("chapters_checked"):
        video.pop("chapters_checked", None)
    url = str(video.get("url") or job.get("source_path") or "").strip()
    if enrich and url and video_metadata_needs_enrichment(video):
        try:
            before_chapters = list(video.get("chapters") or [])
            enriched = enrich_video_payload(url, video)
            if (
                enriched != video
                or list(enriched.get("chapters") or []) != before_chapters
            ):
                method, language = load_job_ingest_meta(job_id)
                save_job_ingest_meta(job_id, method, language, enriched)
                video = enriched
        except Exception:
            logging.exception("youtube metadata enrichment failed for job %s", job_id)
    if video.get("duration_s") is None and segments:
        duration_s = _duration_from_segments(segments)
        if duration_s is not None:
            video["duration_s"] = round(duration_s, 1)
    video.pop("metadata_enriched", None)
    video.pop("chapters_checked", None)
    job["youtube"] = video


def save_job_ingest_meta(
    job_id: int,
    method: YoutubeMethod,
    language: str,
    video: dict | None = None,
    *,
    db=None,
) -> None:
    database = _resolve_meta_db(db)
    existing = database.get_job_youtube_meta(job_id) or {}
    if video is None:
        video_payload = dict(existing.get("video") or {})
    else:
        video_payload = dict(video)
    database.upsert_job_youtube_meta(job_id, method, language or "ru", video_payload)


def load_job_ingest_meta(job_id: int, *, db=None) -> tuple[YoutubeMethod, str]:
    row = _resolve_meta_db(db).get_job_youtube_meta(job_id)
    if not row:
        method: YoutubeMethod = "apify" if apify_api_key() else "ytdlp"
        return method, "ru"
    method_value = str(row.get("method") or "apify").strip().lower()
    if method_value not in {"apify", "ytdlp"}:
        method_value = "apify"
    language = str(row.get("language") or "ru").strip() or "ru"
    return method_value, language


def delete_job_ingest_meta(job_id: int, *, db=None) -> None:
    _resolve_meta_db(db).delete_job_youtube_meta(job_id)


def load_youtube_audio_path(job_id: int) -> Path | None:
    video = load_job_youtube_video(job_id)
    if not video:
        return None
    raw = str(video.get("audio_path") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if is_usable_audio_file(path) else None


def save_youtube_audio_path(job_id: int, audio_path: Path, *, db=None) -> None:
    method, language = load_job_ingest_meta(job_id, db=db)
    video = dict(load_job_youtube_video(job_id, db=db) or {})
    video["audio_path"] = str(audio_path)
    save_job_ingest_meta(job_id, method, language, video, db=db)


def ensure_youtube_audio(
    job_id: int,
    url: str,
    *,
    cancelled: Callable[[], bool] | None = None,
    ytdlp_procs: dict | None = None,
) -> Path:
    from slysh.speakers import SpeakerCancelledError
    from slysh.youtube_ytdlp import YoutubeYtdlpError, download_audio_ytdlp

    existing = load_youtube_audio_path(job_id)
    if existing is not None:
        return existing
    if cancelled and cancelled():
        raise SpeakerCancelledError()
    out_dir = youtube_dir() / "audio" / str(job_id)
    try:
        audio_path = download_audio_ytdlp(
            url,
            out_dir,
            cancelled=cancelled,
            ytdlp_procs=ytdlp_procs,
            job_id=job_id,
        )
    except SpeakerCancelledError:
        raise
    except YoutubeYtdlpError as exc:
        raise YoutubeIngestError(str(exc)) from exc
    save_youtube_audio_path(job_id, audio_path)
    return audio_path


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path or ""
    if host in {"youtu.be"}:
        candidate = path.strip("/").split("/")[0]
        return candidate if _VIDEO_ID_RE.fullmatch(candidate or "") else None
    if host.endswith("youtube.com"):
        if path.startswith("/shorts/"):
            candidate = path.split("/")[2] if len(path.split("/")) > 2 else ""
            return candidate if _VIDEO_ID_RE.fullmatch(candidate or "") else None
        if path.startswith("/watch"):
            query = parse_qs(parsed.query)
            candidate = (query.get("v") or [""])[0]
            return candidate if _VIDEO_ID_RE.fullmatch(candidate or "") else None
        if path.startswith("/embed/"):
            candidate = path.split("/")[2] if len(path.split("/")) > 2 else ""
            return candidate if _VIDEO_ID_RE.fullmatch(candidate or "") else None
    return None


def normalize_youtube_url(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        raise YoutubeIngestError("Укажите ссылку на YouTube.")
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    video_id = extract_video_id(text)
    if not video_id:
        raise YoutubeIngestError("Некорректная ссылка YouTube.")
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    return canonical, video_id


def youtube_status() -> dict:
    auth_mode = cookies_auth_mode()
    return {
        "apify_key_set": bool(apify_api_key()),
        "cookies_present": cookies_present(),
        "cookies_auth_mode": auth_mode,
        "cookies_from_browser": auth_mode == "browser",
        "ytdlp_found": bool(find_ytdlp()),
        "browser_cookie3": browser_cookie3_available(),
        "transcript_api": transcript_api_available(),
    }


def _fetch_ytdlp_with_fallbacks(url: str, language: str) -> dict:
    ytdlp_error: YoutubeYtdlpError | None = None
    try:
        return fetch_transcript_ytdlp(url, language=language)
    except YoutubeYtdlpError as exc:
        ytdlp_error = exc

    api_message = ""
    if transcript_api_available():
        try:
            return fetch_transcript_api(url, language=language)
        except YoutubeTranscriptApiError as exc:
            api_message = str(exc)

    if apify_api_key():
        try:
            return fetch_transcript_apify(url, language=language)
        except YoutubeApifyError as apify_exc:
            parts = [str(ytdlp_error)]
            if api_message:
                parts.append(api_message)
            parts.append(str(apify_exc))
            raise YoutubeIngestError(". ".join(parts)) from apify_exc

    hint = str(ytdlp_error)
    if api_message:
        hint = f"{hint}. {api_message}"
    hint = (
        f"{hint} Для таких видео часто помогает метод Apify (ключ в настройках)."
    )
    raise YoutubeIngestError(hint) from ytdlp_error


def fetch_transcript(
    raw_url: str,
    method: YoutubeMethod,
    language: str = "ru",
) -> YoutubeTranscriptResult:
    url, video_id = normalize_youtube_url(raw_url)
    lang = (language or "ru").strip() or "ru"
    if method == "apify":
        try:
            payload = fetch_transcript_apify(url, language=lang)
        except YoutubeApifyError as exc:
            raise YoutubeIngestError(str(exc)) from exc
    elif method == "ytdlp":
        try:
            payload = _fetch_ytdlp_with_fallbacks(url, lang)
        except YoutubeIngestError:
            raise
        except YoutubeYtdlpError as exc:
            raise YoutubeIngestError(str(exc)) from exc
    else:
        raise YoutubeIngestError(f"Неизвестный способ: {method}")

    from slysh.youtube_metadata import enrich_video_payload

    payload = enrich_video_payload(url, payload)
    segments = merge_segments(payload.get("segments") or [])
    if not segments:
        raise YoutubeIngestError("Субтитры не найдены.")

    title = str(payload.get("title") or "").strip() or f"YouTube {video_id}"
    channel = str(payload.get("channel") or "").strip()
    channel_url = str(payload.get("channel_url") or "").strip()
    upload_date = str(payload.get("upload_date") or "").strip()
    duration_raw = payload.get("duration_s", payload.get("duration"))
    duration_s = float(duration_raw) if duration_raw is not None else None
    chapters_raw = payload.get("chapters") or []
    chapters: tuple[dict, ...] = tuple(
        dict(chapter) for chapter in chapters_raw if isinstance(chapter, dict)
    )
    thumbnail_url = str(payload.get("thumbnail_url") or "").strip()
    if not thumbnail_url:
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return YoutubeTranscriptResult(
        title=title,
        channel=channel,
        channel_url=channel_url,
        upload_date=upload_date,
        video_id=video_id,
        url=url,
        segments=segments,
        duration_s=duration_s,
        chapters=chapters,
        thumbnail_url=thumbnail_url,
    )


def run_youtube_job(
    db,
    job_id: int,
    url: str,
    method: YoutubeMethod,
    language: str,
    *,
    cancel_event: threading.Event | None = None,
) -> None:
    from slysh.models import JobStatus

    def cancelled() -> bool:
        if cancel_event is not None and cancel_event.is_set():
            return True
        current = db.get_job(job_id) or {}
        return current.get("status") == JobStatus.CANCELLED.value

    def report(value: float) -> None:
        if cancelled():
            return
        db.set_progress(job_id, min(1.0, max(0.0, value)))

    def ticker(stop: threading.Event, *, floor: float = 0.15, cap: float = 0.75) -> None:
        value = floor
        while not stop.wait(1.0):
            if cancelled():
                return
            value = min(cap, value + 0.03)
            report(value)
            if value >= cap:
                return

    db.set_status(job_id, JobStatus.RUNNING)
    report(0.05)
    report(0.15)
    stop_ticker = threading.Event()
    ticker_thread = threading.Thread(
        target=ticker,
        args=(stop_ticker,),
        daemon=True,
    )
    ticker_thread.start()
    try:
        try:
            result = fetch_transcript(url, method=method, language=language)
        except YoutubeIngestError as exc:
            if cancelled():
                return
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            return
        except Exception as exc:
            if cancelled():
                return
            logging.exception("youtube job %s failed", job_id)
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            return
    finally:
        stop_ticker.set()
        ticker_thread.join(timeout=1.0)

    if cancelled():
        current = db.get_job(job_id) or {}
        if current.get("status") != JobStatus.CANCELLED.value:
            db.set_status(job_id, JobStatus.CANCELLED)
        return

    report(0.82)
    db.replace_segments(job_id, result.segments)
    db.set_job_source_title(job_id, result.title)
    save_job_ingest_meta(
        job_id,
        method,
        language,
        youtube_video_meta(result),
        db=db,
    )
    report(0.95)
    report(1.0)
    db.set_status(job_id, JobStatus.COMPLETED)
