from __future__ import annotations

import json
import logging
import re
import threading
import time
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
INGEST_ERROR_META_KEY = "_ingest_error"

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_meta_db: object | None = None
_meta_db_lock = threading.Lock()
_PROBE_CACHE: tuple[str, float, bool] | None = None
_PROBE_TTL_S = 45.0


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
    if not isinstance(video, dict):
        return None
    payload = dict(video)
    payload.pop(INGEST_ERROR_META_KEY, None)
    return payload


def load_youtube_ingest_error(job_id: int, *, db=None) -> dict | None:
    row = _resolve_meta_db(db).get_job_youtube_meta(job_id)
    if not row:
        return None
    video = row.get("video")
    if not isinstance(video, dict):
        return None
    raw = video.get(INGEST_ERROR_META_KEY)
    if not isinstance(raw, dict):
        return None
    return {
        "code": str(raw.get("code") or "generic"),
        "hints": [str(h) for h in (raw.get("hints") or []) if str(h).strip()],
        "detail": str(raw.get("detail") or ""),
    }


def save_youtube_ingest_error(
    job_id: int,
    formatted: dict,
    method: YoutubeMethod,
    language: str,
    *,
    db=None,
) -> None:
    row = _resolve_meta_db(db).get_job_youtube_meta(job_id) or {}
    video_payload = dict(row.get("video") or {})
    if not video_payload:
        existing = load_job_youtube_video(job_id, db=db)
        if existing:
            video_payload = dict(existing)
    video_payload[INGEST_ERROR_META_KEY] = {
        "code": formatted.get("code") or "generic",
        "hints": list(formatted.get("hints") or []),
        "detail": str(formatted.get("detail") or ""),
    }
    save_job_ingest_meta(job_id, method, language, video_payload, db=db)


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
    db=None,
) -> None:
    if str(job.get("kind") or "") != "youtube":
        return
    from slysh.youtube_metadata import (
        enrich_video_payload,
        video_metadata_needs_enrichment,
    )

    job_id = int(job["id"])
    video = load_job_youtube_video(job_id, db=db) or fallback_youtube_video_from_job(job)
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
                method, language = load_job_ingest_meta(job_id, db=db)
                save_job_ingest_meta(job_id, method, language, enriched, db=db)
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
    err = load_youtube_ingest_error(job_id, db=db)
    if err:
        job["youtube_error"] = err


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


def youtube_proxy_active() -> bool:
    from slysh.http_proxy import load_proxy_config, should_use_proxy_for_target

    if not should_use_proxy_for_target("youtube"):
        return False
    host = str(load_proxy_config().get("host") or "").strip()
    return bool(host)


def _probe_cache_key() -> str:
    from slysh.http_proxy import load_proxy_config

    cfg = load_proxy_config()
    targets = cfg.get("targets") if isinstance(cfg.get("targets"), dict) else {}
    return json.dumps(
        {
            "enabled": bool(cfg.get("enabled")),
            "host": str(cfg.get("host") or "").strip(),
            "port": cfg.get("port"),
            "youtube": bool(targets.get("youtube")),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _probe_youtube_reachable_live(*, timeout: float = 8.0) -> bool:
    from slysh.http_proxy import opener_for_target

    try:
        import urllib.request

        open_url = opener_for_target("youtube")
        request = urllib.request.Request(
            "https://www.youtube.com/generate_204",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Slysh/1.0"
                ),
            },
        )
        with open_url(request, timeout=timeout) as response:
            code = getattr(response, "status", None) or response.getcode()
            return 200 <= int(code) < 500
    except Exception:
        logging.debug("youtube reachability probe failed", exc_info=True)
        return False


def probe_youtube_reachable(*, timeout: float = 8.0, use_cache: bool = True) -> bool:
    global _PROBE_CACHE

    key = _probe_cache_key()
    now = time.monotonic()
    if (
        use_cache
        and _PROBE_CACHE is not None
        and _PROBE_CACHE[0] == key
        and (now - _PROBE_CACHE[1]) < _PROBE_TTL_S
    ):
        return _PROBE_CACHE[2]
    result = _probe_youtube_reachable_live(timeout=timeout)
    _PROBE_CACHE = (key, now, result)
    return result


def reset_youtube_reachability_cache_for_tests() -> None:
    global _PROBE_CACHE
    _PROBE_CACHE = None


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
        "youtube_proxy_active": youtube_proxy_active(),
        "youtube_reachable": probe_youtube_reachable(),
    }


def _fetch_ytdlp_with_fallbacks(url: str, language: str) -> dict:
    from slysh.http_proxy import should_use_proxy_for_target
    from slysh.youtube_errors import format_youtube_failure

    ytdlp_error: YoutubeYtdlpError | None = None
    try:
        return fetch_transcript_ytdlp(url, language=language)
    except YoutubeYtdlpError as exc:
        ytdlp_error = exc

    reachable = probe_youtube_reachable()
    proxy_active = should_use_proxy_for_target("youtube")
    api_message = ""
    try_transcript_api = transcript_api_available() and (reachable or proxy_active)
    if try_transcript_api:
        try:
            return fetch_transcript_api(url, language=language)
        except YoutubeTranscriptApiError as exc:
            api_message = str(exc)
    elif transcript_api_available() and not reachable and not proxy_active:
        api_message = "YouTube недоступен из текущей сети (проверка перед fallback)."

    if apify_api_key():
        try:
            return fetch_transcript_apify(url, language=language)
        except YoutubeApifyError as apify_exc:
            combined = str(ytdlp_error)
            if api_message:
                combined = f"{combined}. {api_message}. {apify_exc}"
            else:
                combined = f"{combined}. {apify_exc}"
            formatted = format_youtube_failure(combined, method="ytdlp")
            raise YoutubeIngestError(formatted["message"]) from apify_exc

    combined = str(ytdlp_error)
    if api_message:
        combined = f"{combined}. {api_message}"
    formatted = format_youtube_failure(combined, method="ytdlp")
    raise YoutubeIngestError(formatted["message"]) from ytdlp_error


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
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    from slysh.asr_coordinator import job_run_active, job_run_id
    from slysh.models import JobStatus
    from slysh.youtube_errors import format_youtube_failure
    from slysh.youtube_ytdlp import YTDLP_FETCH_WALL_CLOCK_S

    run_id = job_run_id(db, job_id)

    def fail_job(exc: BaseException) -> None:
        formatted = format_youtube_failure(exc, method=method)
        db.set_error(job_id, formatted["message"])
        save_youtube_ingest_error(job_id, formatted, method, language, db=db)
        db.set_status(job_id, JobStatus.FAILED)

    def cancelled() -> bool:
        if cancel_event is not None and cancel_event.is_set():
            return True
        if not job_run_active(db, job_id, run_id):
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
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    fetch_transcript,
                    url,
                    method=method,
                    language=language,
                )
                try:
                    result = future.result(timeout=YTDLP_FETCH_WALL_CLOCK_S)
                except FuturesTimeoutError as exc:
                    if cancelled():
                        return
                    fail_job(
                        TimeoutError(
                            "Превышено время ожидания ответа от YouTube (wall-clock)."
                        )
                    )
                    return
        except YoutubeIngestError as exc:
            if cancelled():
                return
            fail_job(exc)
            return
        except Exception as exc:
            if cancelled():
                return
            logging.exception("youtube job %s failed", job_id)
            fail_job(exc)
            return
    finally:
        stop_ticker.set()
        ticker_thread.join(timeout=1.0)

    if cancelled():
        current = db.get_job(job_id) or {}
        if current.get("status") != JobStatus.CANCELLED.value:
            db.set_status(job_id, JobStatus.CANCELLED)
        return

    if not job_run_active(db, job_id, run_id):
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
    from slysh.job_media_duration import refresh_media_duration

    refresh_media_duration(db, job_id)
