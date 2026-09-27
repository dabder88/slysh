from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from slysh.http_proxy import opener_for_target

from slysh.models import Segment
from slysh.providers import apify_api_key
from slysh.vtt import parse_srt, parse_srt_plain

APIFY_PRIMARY_ACTOR_ID = "scrapesage~youtube-transcript-scraper"
APIFY_FALLBACK_ACTOR_ID = "h7sDV53CddomktSi5"
APIFY_RUN_SYNC_URL = "https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"


class YoutubeApifyError(Exception):
    """Raised when Apify transcript fetch fails."""


def _seconds_to_ms(value: Any) -> int:
    try:
        return int(float(value) * 1000)
    except (TypeError, ValueError):
        return 0


def _segments_from_apify_item(item: dict) -> list[Segment]:
    raw_segments = item.get("segments")
    if not isinstance(raw_segments, list):
        return []
    out: list[Segment] = []
    for row in raw_segments:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        start_ms = _seconds_to_ms(row.get("start"))
        end_ms = _seconds_to_ms(row.get("end"))
        if end_ms <= start_ms and row.get("dur") is not None:
            end_ms = start_ms + _seconds_to_ms(row.get("dur"))
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        out.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
    return out


def _segments_from_subtitles_field(subs: Any, language: str) -> list[Segment]:
    if isinstance(subs, str) and subs.strip():
        segments = parse_srt(subs)
        if segments:
            return segments
        plain = parse_srt_plain(subs).strip()
        return [Segment(0, 1000, plain)] if plain else []

    if not isinstance(subs, list) or not subs:
        return []

    preferred = language.lower()
    chosen = next(
        (
            row
            for row in subs
            if isinstance(row, dict) and str(row.get("language") or "").lower() == preferred
        ),
        None,
    )
    if chosen is None:
        chosen = subs[0] if isinstance(subs[0], dict) else None
    if not isinstance(chosen, dict):
        return []

    srt_text = str(chosen.get("srt") or chosen.get("text") or "").strip()
    if not srt_text:
        return []
    segments = parse_srt(srt_text)
    if segments:
        return segments
    plain = parse_srt_plain(srt_text).strip()
    return [Segment(0, 1000, plain)] if plain else []


def _segments_from_transcript_text(item: dict) -> list[Segment]:
    transcript = str(item.get("transcript") or item.get("text") or "").strip()
    if not transcript:
        return []
    return [Segment(0, 1000, transcript)]


def _pick_item(payload: Any) -> dict:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _call_apify_actor(actor_id: str, body: dict, token: str) -> Any:
    url = APIFY_RUN_SYNC_URL.format(actor_id=actor_id)
    request = Request(
        f"{url}?token={token}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener_for_target("youtube")(request, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise YoutubeApifyError(f"Apify HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise YoutubeApifyError(f"Не удалось связаться с Apify: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise YoutubeApifyError("Apify вернул некорректный JSON.") from exc


def _metadata_from_item(item: dict) -> dict[str, str]:
    metadata = item.get("videoMetadata")
    if not isinstance(metadata, dict):
        metadata = item

    title = str(
        metadata.get("title")
        or item.get("title")
        or item.get("videoTitle")
        or ""
    ).strip()
    channel = str(
        metadata.get("channelName")
        or metadata.get("channel")
        or item.get("channelTitle")
        or item.get("channelName")
        or item.get("channel")
        or ""
    ).strip()
    upload_date = str(
        metadata.get("uploadDate")
        or metadata.get("date")
        or metadata.get("publishedAt")
        or metadata.get("datePublished")
        or item.get("uploadDate")
        or item.get("publishedDate")
        or item.get("publishedAt")
        or item.get("date")
        or ""
    ).strip()
    if upload_date:
        upload_date = upload_date[:10].replace("/", "-")
    duration_raw = (
        metadata.get("duration")
        or metadata.get("durationSeconds")
        or item.get("duration")
        or item.get("durationSeconds")
    )
    duration_s = float(duration_raw) if duration_raw is not None else None
    channel_url = str(
        metadata.get("channelUrl")
        or metadata.get("channel_url")
        or item.get("channelUrl")
        or ""
    ).strip()
    thumbnail_url = str(
        metadata.get("thumbnailUrl")
        or metadata.get("thumbnail")
        or item.get("thumbnailUrl")
        or item.get("thumbnail")
        or ""
    ).strip()
    chapters: list[dict] = []
    for chapter in metadata.get("chapters") or item.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_title = str(chapter.get("title") or chapter.get("name") or "").strip()
        start = chapter.get("startMs")
        if start is None:
            start = chapter.get("start_ms")
        if start is None:
            start_value = chapter.get("start") or chapter.get("startTime")
            if start_value is not None:
                start = int(float(start_value) * 1000)
        if not chapter_title or start is None:
            continue
        chapters.append({"title": chapter_title, "start_ms": int(start)})
    return {
        "title": title,
        "channel": channel,
        "channel_url": channel_url,
        "upload_date": upload_date,
        "duration_s": duration_s,
        "chapters": chapters,
        "thumbnail_url": thumbnail_url,
    }


def _segments_from_item(item: dict, language: str) -> list[Segment]:
    segments = _segments_from_apify_item(item)
    if segments:
        return segments
    segments = _segments_from_transcript_text(item)
    if segments:
        return segments
    return _segments_from_subtitles_field(item.get("subtitles"), language)


def _fetch_primary(url: str, language: str, token: str) -> dict:
    payload = _call_apify_actor(
        APIFY_PRIMARY_ACTOR_ID,
        {
            "videoUrls": [url],
            "language": language or "ru",
            "includeSegments": True,
            "includeVideoMetadata": True,
            "maxResults": 1,
            "maxVideosPerSource": 1,
        },
        token,
    )
    item = _pick_item(payload)
    if not item:
        raise YoutubeApifyError("Apify не вернул данные по этому видео.")
    segments = _segments_from_item(item, language)
    if not segments:
        raise YoutubeApifyError("Субтитры не найдены в ответе основного актора Apify.")
    meta = _metadata_from_item(item)
    return {**meta, "segments": segments}


def _fetch_fallback(url: str, language: str, token: str) -> dict:
    payload = _call_apify_actor(
        APIFY_FALLBACK_ACTOR_ID,
        {
            "startUrls": [{"url": url}],
            "downloadSubtitles": True,
            "subtitlesLanguage": language or "ru",
            "subtitlesFormat": "srt",
            "preferAutoGeneratedSubtitles": True,
            "maxResults": 1,
        },
        token,
    )
    item = _pick_item(payload)
    if not item:
        raise YoutubeApifyError("Apify (резервный актор) не вернул данные по этому видео.")
    segments = _segments_from_item(item, language)
    if not segments:
        raise YoutubeApifyError("Субтитры не найдены в ответе резервного актора Apify.")
    meta = _metadata_from_item(item)
    return {**meta, "segments": segments}


def fetch_transcript_apify(url: str, language: str = "ru") -> dict:
    token = apify_api_key()
    if not token:
        raise YoutubeApifyError(
            "Не задан API-ключ Apify. Укажите его в настройках или переменной APIFY_API_TOKEN."
        )
    lang = (language or "ru").strip() or "ru"
    try:
        return _fetch_primary(url, lang, token)
    except YoutubeApifyError as primary_error:
        logging.warning("Apify primary actor failed: %s", primary_error)
        try:
            return _fetch_fallback(url, lang, token)
        except YoutubeApifyError as fallback_error:
            raise YoutubeApifyError(
                f"{primary_error}. Резервный актор: {fallback_error}"
            ) from fallback_error
