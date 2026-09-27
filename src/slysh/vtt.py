from __future__ import annotations

import re

from slysh.models import Segment

from slysh.chunking import CHUNK_SECONDS

_TAG_RE = re.compile(r"<[^>]+>")
_SRT_TIME_RE = re.compile(
    r"^(?P<start>\d+:\d+:\d+[,\.]\d+)\s*-->\s*(?P<end>\d+:\d+:\d+[,\.]\d+)",
    re.MULTILINE,
)
_TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
    r"\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
)


def _clock_to_ms(value: str) -> int:
    text = value.strip()
    parts = text.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"invalid timestamp: {value}")
    sec_parts = seconds.split(".")
    whole = int(sec_parts[0])
    frac = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    if len(sec_parts) > 1 and len(sec_parts[1]) == 2:
        frac *= 10
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + whole * 1_000
        + frac
    )


def _clean_cue_text(text: str) -> str:
    cleaned = _TAG_RE.sub("", text)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = cleaned.replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(cleaned.split())


def parse_vtt(text: str) -> list[Segment]:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[Segment] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
            index += 1
            continue
        if line.isdigit():
            index += 1
            if index >= len(lines):
                break
            line = lines[index].strip()
        match = _TIMESTAMP_RE.match(line)
        if match is None:
            index += 1
            continue
        start_ms = _clock_to_ms(match.group("start"))
        end_ms = _clock_to_ms(match.group("end"))
        index += 1
        body_parts: list[str] = []
        while index < len(lines) and lines[index].strip():
            body_parts.append(lines[index].strip())
            index += 1
        body = _clean_cue_text(" ".join(body_parts))
        if body:
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=body))
        index += 1
    return segments


def _srt_clock_to_ms(value: str) -> int:
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid srt timestamp: {value}")
    hours, minutes, seconds = parts
    sec_parts = seconds.split(".")
    whole = int(sec_parts[0])
    frac = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    if len(sec_parts) > 1 and len(sec_parts[1]) == 2:
        frac *= 10
    return int(hours) * 3_600_000 + int(minutes) * 60_000 + whole * 1_000 + frac


def parse_srt(text: str) -> list[Segment]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    segments: list[Segment] = []
    blocks = re.split(r"\n\s*\n", normalized)
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        time_index = 1 if lines[0].isdigit() else 0
        if time_index >= len(lines):
            continue
        match = _SRT_TIME_RE.match(lines[time_index])
        if match is None:
            continue
        start_ms = _srt_clock_to_ms(match.group("start"))
        end_ms = _srt_clock_to_ms(match.group("end"))
        body = _clean_cue_text(" ".join(lines[time_index + 1 :]))
        if not body:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=body))
    return segments


def parse_srt_plain(text: str) -> str:
    return " ".join(segment.text for segment in parse_srt(text))


def merge_segments(
    segments: list[Segment],
    target_ms: int = CHUNK_SECONDS * 1000,
    max_gap_ms: int = 1500,
    max_ms: int = CHUNK_SECONDS * 1000 + 5000,
) -> list[Segment]:
    """Склеивает короткие реплики субтитров в блоки ~CHUNK_SECONDS, как у GigaAM."""
    if len(segments) <= 1:
        return list(segments)

    merged: list[Segment] = []
    buf_start = segments[0].start_ms
    buf_end = segments[0].end_ms
    buf_parts = [segments[0].text.strip()]

    for segment in segments[1:]:
        text = segment.text.strip()
        if not text:
            continue
        gap_ms = max(0, segment.start_ms - buf_end)
        span_ms = buf_end - buf_start
        next_span = segment.end_ms - buf_start
        should_flush = (
            span_ms >= target_ms
            or next_span > max_ms
            or gap_ms > max_gap_ms
        )
        if should_flush:
            merged.append(
                Segment(buf_start, buf_end, " ".join(part for part in buf_parts if part))
            )
            buf_start = segment.start_ms
            buf_end = segment.end_ms
            buf_parts = [text]
            continue
        buf_parts.append(text)
        buf_end = max(buf_end, segment.end_ms)

    if buf_parts:
        merged.append(
            Segment(buf_start, buf_end, " ".join(part for part in buf_parts if part))
        )
    return merged
