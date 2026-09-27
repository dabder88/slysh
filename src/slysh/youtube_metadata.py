from __future__ import annotations

import json
import re
from urllib.parse import quote, parse_qs, urlparse
from urllib.request import Request

from slysh.http_proxy import opener_for_target

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_WATCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
_RU_MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "мая": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "сент": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}
_CHAPTER_LINE_RE = re.compile(r"^(\d{1,2}(?::\d{2}){1,2})\s+(.+)$")


def _extract_video_id(url: str) -> str | None:
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
    return None


def _walk_yt_nodes(obj, renderer_name: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(obj, dict):
        node = obj.get(renderer_name)
        if isinstance(node, dict):
            found.append(node)
        for value in obj.values():
            found.extend(_walk_yt_nodes(value, renderer_name))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_walk_yt_nodes(value, renderer_name))
    return found


def _extract_json_blob(html: str, marker: str) -> dict | None:
    idx = html.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    depth = 0
    for i, ch in enumerate(html[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None


def _simple_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("simpleText") or "").strip()
    return ""


def _parse_hms_timestamp(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(parts) == 2:
        minutes, seconds = numbers
        return (minutes * 60 + seconds) * 1000
    if len(parts) == 3:
        hours, minutes, seconds = numbers
        return (hours * 3600 + minutes * 60 + seconds) * 1000
    return None


def _parse_ru_duration_seconds(label: str) -> int | None:
    text = label.strip().lower()
    if not text:
        return None
    if text.startswith("0 сек"):
        return 0
    total = 0
    for match in re.finditer(r"(\d+)\s*(час|мин|сек)", text):
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("час"):
            total += amount * 3600
        elif unit.startswith("мин"):
            total += amount * 60
        else:
            total += amount
    return total if total or "0 сек" in text else None


def _chapter_start_ms(time_description) -> int | None:
    if isinstance(time_description, dict):
        simple = _simple_text(time_description.get("simpleText"))
        if simple:
            parsed = _parse_hms_timestamp(simple)
            if parsed is not None:
                return parsed
        accessibility = time_description.get("accessibility", {})
        if isinstance(accessibility, dict):
            label = str(
                accessibility.get("accessibilityData", {}).get("label") or ""
            ).strip()
            seconds = _parse_ru_duration_seconds(label)
            if seconds is not None:
                return seconds * 1000
    elif isinstance(time_description, str):
        parsed = _parse_hms_timestamp(time_description)
        if parsed is not None:
            return parsed
    return None


def _chapters_from_initial_data(data: dict) -> list[dict]:
    chapters: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for item in _walk_yt_nodes(data, "macroMarkersListItemRenderer"):
        title = _simple_text(item.get("title"))
        start_ms = _chapter_start_ms(item.get("timeDescription"))
        if not title or start_ms is None:
            continue
        key = (title, start_ms)
        if key in seen:
            continue
        seen.add(key)
        chapters.append({"title": title, "start_ms": start_ms})
    chapters.sort(key=lambda chapter: chapter["start_ms"])
    return chapters


def _chapters_from_description(text: str) -> list[dict]:
    chapters: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for line in text.splitlines():
        match = _CHAPTER_LINE_RE.match(line.strip())
        if not match:
            continue
        start_ms = _parse_hms_timestamp(match.group(1))
        title = match.group(2).strip()
        if start_ms is None or not title:
            continue
        key = (start_ms, title)
        if key in seen:
            continue
        seen.add(key)
        chapters.append({"title": title, "start_ms": start_ms})
    chapters.sort(key=lambda chapter: chapter["start_ms"])
    return chapters


def _description_from_watch_html(html: str, initial_data: dict | None) -> str:
    player = _extract_json_blob(html, "var ytInitialPlayerResponse = ")
    if not player:
        player = _extract_json_blob(html, "ytInitialPlayerResponse = ")
    if player:
        description = str(
            player.get("videoDetails", {}).get("shortDescription") or ""
        ).strip()
        if description:
            return description
    if not initial_data:
        return ""
    for renderer in _walk_yt_nodes(
        initial_data, "expandableVideoDescriptionBodyRenderer"
    ):
        pieces: list[str] = []
        for node in _walk_yt_nodes(renderer, "text"):
            if not isinstance(node, dict):
                continue
            text = _simple_text(node)
            if text:
                pieces.append(text)
        if pieces:
            return "\n".join(pieces)
    return ""


def _chapters_from_watch_html(html: str, initial_data: dict | None) -> list[dict]:
    chapters = []
    if initial_data:
        chapters = _chapters_from_initial_data(initial_data)
    if chapters:
        return chapters
    description = _description_from_watch_html(html, initial_data)
    return _chapters_from_description(description)


def _parse_ru_date_text(value: str) -> str:
    cleaned = value.replace("\u202f", " ").strip().rstrip(".")
    match = re.search(r"(\d{1,2})\s+([а-яё]+)\.?\s+(\d{4})", cleaned, re.IGNORECASE)
    if not match:
        return ""
    day = int(match.group(1))
    month_token = match.group(2).lower().rstrip(".")
    year = int(match.group(3))
    month = _RU_MONTHS.get(month_token[:4]) or _RU_MONTHS.get(month_token[:3])
    if not month:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _collect_date_texts(obj, found: list[str] | None = None) -> list[str]:
    if found is None:
        found = []
    if isinstance(obj, dict):
        date_text = obj.get("dateText")
        if isinstance(date_text, dict):
            text = _simple_text(date_text)
            if text:
                found.append(text)
        for value in obj.values():
            _collect_date_texts(value, found)
    elif isinstance(obj, list):
        for value in obj:
            _collect_date_texts(value, found)
    return found


def _upload_date_from_initial_data(data: dict) -> str:
    for renderer in _walk_yt_nodes(data, "playerMicroformatRenderer"):
        for key in ("publishDate", "uploadDate"):
            raw = str(renderer.get(key) or "").strip()
            if raw:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                    return raw
                if re.fullmatch(r"\d{8}", raw):
                    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    for text in _collect_date_texts(data):
        parsed = _parse_ru_date_text(text)
        if parsed:
            return parsed
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
    return ""


def fetch_video_metadata_watch_page(url: str) -> dict:
    video_id = _extract_video_id(url)
    if not video_id:
        return {}
    request = Request(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={
            "User-Agent": _WATCH_USER_AGENT,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        },
    )
    try:
        with opener_for_target("youtube")(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
    except OSError:
        return {}

    initial_data = _extract_json_blob(html, "var ytInitialData = ")
    if not initial_data:
        initial_data = _extract_json_blob(html, "ytInitialData = ")
    if not initial_data:
        return {"chapters_checked": True}

    chapters = _chapters_from_watch_html(html, initial_data)
    upload_date = _upload_date_from_initial_data(initial_data)
    result: dict = {"chapters_checked": True}
    if upload_date:
        result["upload_date"] = upload_date
    if chapters:
        result["chapters"] = chapters
    return result


def fetch_video_metadata_oembed(url: str) -> dict:
    video_id = _extract_video_id(url)
    if not video_id:
        return {}
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    request = Request(
        f"https://www.youtube.com/oembed?url={quote(watch_url, safe='')}&format=json",
        headers={"User-Agent": "Mozilla/5.0 (compatible; Slysh/1.0)"},
    )
    try:
        with opener_for_target("youtube")(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "title": str(data.get("title") or "").strip(),
        "channel": str(data.get("author_name") or "").strip(),
        "channel_url": str(data.get("author_url") or "").strip(),
        "thumbnail_url": str(data.get("thumbnail_url") or "").strip(),
        "upload_date": "",
        "duration_s": None,
        "chapters": [],
    }


def _title_matches_chapter_title(video: dict) -> bool:
    title = str(video.get("title") or "").strip().casefold()
    if not title:
        return False
    for chapter in video.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_title = str(chapter.get("title") or "").strip().casefold()
        if chapter_title and chapter_title == title:
            return True
    return False


def merge_video_metadata(payload: dict, extra: dict) -> dict:
    merged = dict(payload)
    for key, value in extra.items():
        current = merged.get(key)
        if key == "chapters":
            if not merged.get("chapters") and value:
                merged["chapters"] = value
            continue
        if key == "chapters_checked":
            if value:
                merged["chapters_checked"] = True
            continue
        if key == "duration_s":
            if merged.get("duration_s") is None and value is not None:
                merged["duration_s"] = value
            continue
        if not str(current or "").strip() and value not in (None, "", []):
            merged[key] = value
    return merged


def enrich_video_payload(url: str, payload: dict) -> dict:
    from slysh.youtube_ytdlp import fetch_video_metadata_ytdlp

    merged = dict(payload)
    if _title_matches_chapter_title(merged):
        merged["title"] = ""
    missing_chapters = not merged.get("chapters")
    missing_upload = not str(merged.get("upload_date") or "").strip()
    missing_title = not str(merged.get("title") or "").strip()
    missing_channel = not str(merged.get("channel") or "").strip()

    if missing_title or missing_channel:
        merged = merge_video_metadata(merged, fetch_video_metadata_oembed(url))
    if missing_chapters or missing_upload:
        merged = merge_video_metadata(merged, fetch_video_metadata_watch_page(url))
    if (
        missing_title
        or missing_channel
        or merged.get("duration_s") is None
        or (missing_chapters and not merged.get("chapters"))
        or (missing_upload and not str(merged.get("upload_date") or "").strip())
    ):
        merged = merge_video_metadata(merged, fetch_video_metadata_ytdlp(url))
    if not merged.get("chapters") and not merged.get("chapters_checked"):
        merged = merge_video_metadata(merged, fetch_video_metadata_watch_page(url))
    video_id = _extract_video_id(url)
    if not str(merged.get("thumbnail_url") or "").strip() and video_id:
        merged["thumbnail_url"] = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    if _video_metadata_complete(merged):
        merged["metadata_enriched"] = True
    return merged


def _video_metadata_complete(video: dict) -> bool:
    if not str(video.get("upload_date") or "").strip():
        return False
    if not video.get("chapters") and not video.get("chapters_checked"):
        return False
    return True


def video_metadata_needs_enrichment(video: dict) -> bool:
    if _title_matches_chapter_title(video):
        return True
    if not str(video.get("channel") or "").strip():
        return True
    if not str(video.get("title") or "").strip():
        return True
    if not str(video.get("upload_date") or "").strip():
        return True
    if video.get("chapters"):
        return False
    return not video.get("chapters_checked")
