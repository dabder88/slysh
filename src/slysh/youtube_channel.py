from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from slysh.youtube_ingest import YoutubeIngestError, extract_video_id, normalize_youtube_url
from slysh.youtube_ytdlp import (
    YoutubeYtdlpError,
    _base_ytdlp_args,
    _run_ytdlp,
    find_ytdlp,
)

Direction = Literal["older", "newer"]


@dataclass(frozen=True)
class YoutubeFeedFilters:
    limit: int | None = None
    date: str | None = None
    dateafter: str | None = None
    datebefore: str | None = None
    start_video: str | None = None
    direction: Direction = "older"


@dataclass(frozen=True)
class YoutubeVideoRef:
    video_id: str
    url: str
    title: str


class YoutubeChannelError(Exception):
    """Raised when channel/playlist listing fails."""


def _canonical_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def resolve_start_video_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise YoutubeChannelError("Укажите ссылку на стартовое видео.")
    if "://" in text or text.startswith("youtu"):
        url = text if text.startswith(("http://", "https://")) else f"https://{text}"
        video_id = extract_video_id(url)
        if not video_id:
            raise YoutubeChannelError("Некорректная ссылка на стартовое видео.")
        return video_id
    return text


def _parse_feed_json_lines(stdout: str) -> list[dict]:
    videos: list[dict] = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("id"):
            videos.append(data)
    return videos


def list_feed_videos(url: str, filters: YoutubeFeedFilters | None = None) -> list[YoutubeVideoRef]:
    """List videos from a channel, @handle, playlist or /videos URL via yt-dlp."""
    if not find_ytdlp():
        raise YoutubeChannelError(
            "yt-dlp не найден. Установите yt-dlp или выполните: uv sync --extra youtube"
        )
    flt = filters or YoutubeFeedFilters()
    cmd = [*_base_ytdlp_args(), "--dump-json", "--match-filter", "original_url!*=/shorts/"]

    has_date_filter = bool(flt.date or flt.dateafter or flt.datebefore)
    if not has_date_filter:
        cmd.append("--flat-playlist")

    if flt.date:
        cmd.extend(["--date", flt.date])
    if flt.dateafter:
        cmd.extend(["--dateafter", flt.dateafter])
    if flt.datebefore:
        cmd.extend(["--datebefore", flt.datebefore])

    if not flt.start_video and flt.limit:
        cmd.extend(["--playlist-end", str(flt.limit)])

    cmd.append(url)

    result = _run_ytdlp([*cmd], timeout=300)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "")[:500]
        raise YoutubeChannelError(f"Не удалось получить список видео: {err}")

    raw = _parse_feed_json_lines(result.stdout)
    if flt.start_video:
        start_id = resolve_start_video_id(flt.start_video)
        start_idx = next((i for i, v in enumerate(raw) if v.get("id") == start_id), -1)
        if start_idx == -1:
            raise YoutubeChannelError(f"Видео с id «{start_id}» не найдено в списке.")
        if flt.direction == "older":
            raw = raw[start_idx:]
        else:
            raw = raw[: start_idx + 1]
            raw.reverse()
        if flt.limit:
            raw = raw[: flt.limit]

    refs: list[YoutubeVideoRef] = []
    for item in raw:
        video_id = str(item.get("id") or "").strip()
        if not video_id:
            continue
        title = str(item.get("title") or "").strip() or video_id
        item_url = (
            str(item.get("url") or item.get("webpage_url") or "").strip()
            or _canonical_watch_url(video_id)
        )
        refs.append(YoutubeVideoRef(video_id=video_id, url=item_url, title=title))
    return refs


def parse_url_lines(text: str) -> list[str]:
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def expand_url_lines(text: str) -> list[YoutubeVideoRef]:
    refs: list[YoutubeVideoRef] = []
    for raw in parse_url_lines(text):
        try:
            url, video_id = normalize_youtube_url(raw)
        except YoutubeIngestError as exc:
            raise YoutubeChannelError(str(exc)) from exc
        refs.append(
            YoutubeVideoRef(
                video_id=video_id,
                url=url,
                title=f"YouTube {video_id}",
            )
        )
    return refs


def dedupe_videos(refs: list[YoutubeVideoRef]) -> list[YoutubeVideoRef]:
    seen: set[str] = set()
    out: list[YoutubeVideoRef] = []
    for ref in refs:
        if ref.video_id in seen:
            continue
        seen.add(ref.video_id)
        out.append(ref)
    return out


def expand_youtube_sources(
    *,
    mode: Literal["lines", "feed"],
    lines: str | None = None,
    feed_url: str | None = None,
    filters: YoutubeFeedFilters | None = None,
) -> list[YoutubeVideoRef]:
    if mode == "lines":
        if not (lines or "").strip():
            raise YoutubeChannelError("Укажите хотя бы один URL (по одному на строку).")
        refs = expand_url_lines(lines or "")
    elif mode == "feed":
        url = (feed_url or "").strip()
        if not url:
            raise YoutubeChannelError("Укажите URL канала или плейлиста.")
        try:
            refs = list_feed_videos(url, filters)
        except YoutubeYtdlpError as exc:
            raise YoutubeChannelError(str(exc)) from exc
    else:
        raise YoutubeChannelError(f"Неизвестный режим: {mode}")
    return dedupe_videos(refs)
