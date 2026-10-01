from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from slysh.models import Segment
from slysh.paths import youtube_dir
from slysh.timestamps import to_timestamp

PARAGRAPH_SPLIT_MS = 2000
ALLOWED_FORMATS = {"txt", "srt", "vtt", "md"}


def normalize_fmt(fmt: str) -> str:
    value = (fmt or "").lower().lstrip(".")
    if value not in ALLOWED_FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    return value


def suggested_export_path(source_path: str, fmt: str) -> Path:
    fmt = normalize_fmt(fmt)
    source = Path(source_path)
    stem = source.stem or "transcript"
    return source.with_name(f"{stem}.{fmt}")


def _export_slot_key(directory: Path, filename: str) -> str:
    dir_key = str(Path(directory).resolve()).casefold()
    return f"{dir_key}\x1f{filename.casefold()}"


def batch_export_stem_candidates(source_path: str) -> tuple[str, ...]:
    """Prefer bare stem; add parent folder suffix before numeric _2, _3."""
    source = Path(source_path)
    base = (source.stem or "transcript").strip() or "transcript"
    parent = (source.parent.name or "").strip()
    if parent and parent not in {".", ".."}:
        return (base, f"{base}__{parent}")
    return (base,)


def unique_export_path(
    directory: Path,
    stem: str,
    fmt: str,
    used: set[str],
    *,
    alt_stems: tuple[str, ...] = (),
) -> Path:
    fmt = normalize_fmt(fmt)
    directory = Path(directory)
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in (stem,) + tuple(alt_stems):
        base = (raw or "transcript").strip() or "transcript"
        key = base.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(base)
    if not candidates:
        candidates = ["transcript"]
    for base in candidates:
        name = f"{base}.{fmt}"
        slot = _export_slot_key(directory, name)
        if slot not in used:
            used.add(slot)
            return directory / name
    primary = candidates[0]
    index = 2
    while True:
        name = f"{primary}_{index}.{fmt}"
        slot = _export_slot_key(directory, name)
        if slot not in used:
            used.add(slot)
            return directory / name
        index += 1


def _yaml_scalar(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _markdown_transcript_timestamps(segments: list[Segment]) -> str:
    blocks: list[str] = []
    for segment in segments:
        start = to_timestamp(segment.start_ms)
        end = to_timestamp(segment.end_ms)
        blocks.append(f"**{start} – {end}**  \n{segment.export_text()}")
    return "\n\n".join(blocks)


def file_job_markdown_meta(job: dict) -> dict[str, str]:
    source_path = str(job.get("source_path") or "")
    title = str(job.get("source_title") or "").strip()
    if not title and source_path:
        title = Path(source_path).stem
    title = title or "transcript"
    kind = str(job.get("kind") or "file").strip().lower() or "file"
    return {"title": title, "source": source_path, "kind": kind}


def youtube_export_meta_from_job(
    job: dict,
    video: dict | None,
    language: str,
) -> dict[str, str]:
    """Legacy ingest metadata (language etc.). MD export uses unified Obsidian layout via write_media_markdown."""
    video = video or {}
    return {
        "title": str(job.get("source_title") or video.get("title") or "YouTube"),
        "channel": str(video.get("channel") or ""),
        "url": str(video.get("url") or job.get("source_path") or ""),
        "upload_date": str(video.get("upload_date") or ""),
        "language": str(language or "ru"),
    }


def is_youtube_markdown_meta(meta: dict) -> bool:
    return bool(meta.get("url") or meta.get("channel") or meta.get("upload_date"))


def _markdown_fields_from_youtube_meta(meta: dict) -> tuple[str, str, str]:
    return (
        str(meta.get("title") or "YouTube"),
        str(meta.get("url") or meta.get("source") or ""),
        "youtube",
    )


def write_output(path: Path, segments: list[Segment], fmt: str) -> None:
    fmt = normalize_fmt(fmt)
    path = Path(path)
    if fmt == "md":
        write_media_markdown(
            path,
            title=path.stem or "transcript",
            source="",
            kind="file",
            segments=segments,
        )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        if fmt == "txt":
            chunks: list[str] = []
            previous_end: int | None = None
            for segment in segments:
                if previous_end is not None and (segment.start_ms - previous_end) >= PARAGRAPH_SPLIT_MS:
                    chunks.append("\n\n")
                elif chunks and not chunks[-1].endswith("\n"):
                    chunks.append(" ")
                chunks.append(segment.export_text())
                previous_end = segment.end_ms
            file.write("".join(chunks).strip() + "\n")
        elif fmt == "vtt":
            file.write("WEBVTT\n\n")
            for segment in segments:
                file.write(
                    f"{to_timestamp(segment.start_ms)} --> {to_timestamp(segment.end_ms)}\n"
                    f"{segment.export_text()}\n\n"
                )
        elif fmt == "srt":
            for i, segment in enumerate(segments, start=1):
                file.write(
                    f"{i}\n"
                    f"{to_timestamp(segment.start_ms, ',')} --> {to_timestamp(segment.end_ms, ',')}\n"
                    f"{segment.export_text()}\n\n"
                )


def sanitize_export_stem(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", name or "")
    cleaned = re.sub(r"-+", "-", cleaned).strip("- ")
    if len(cleaned) > 100:
        cleaned = cleaned[:100].rstrip("- ")
    return cleaned or "transcript"


def youtube_export_stem(job: dict) -> str:
    title = str(job.get("source_title") or "").strip()
    if title:
        return sanitize_export_stem(title)
    path = str(job.get("source_path") or "")
    video_id = path.split("v=")[-1].split("&")[0] if "v=" in path else ""
    if video_id:
        return sanitize_export_stem(f"YouTube {video_id}")
    return "transcript"


def youtube_job_export_path(job: dict, fmt: str, rules: dict) -> Path:
    fmt = normalize_fmt(fmt)
    stem = youtube_export_stem(job)
    if rules.get("export_dir_mode") == "fixed" and rules.get("export_dir"):
        return Path(str(rules["export_dir"])) / f"{stem}.{fmt}"
    return youtube_dir() / "exports" / f"{stem}.{fmt}"


def write_media_markdown(
    path: Path,
    *,
    title: str,
    source: str,
    kind: str,
    segments: list[Segment],
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    safe_title = _yaml_scalar(title)
    safe_source = _yaml_scalar(source)
    safe_kind = _yaml_scalar(kind)
    body = _markdown_transcript_timestamps(segments)
    source_line = f"**Source:** `{source}`\n" if source else ""
    content = f"""---
title: {safe_title}
source: {safe_source}
kind: {safe_kind}
transcribed_at: {json.dumps(today)}
---

# {title}

{source_line}**Kind:** {kind or "file"}

## Transcript

{body}
"""
    path.write_text(content, encoding="utf-8")


def write_job_export(
    path: Path,
    segments: list[Segment],
    fmt: str,
    *,
    youtube_meta: dict | None = None,
    job: dict | None = None,
) -> None:
    fmt = normalize_fmt(fmt)
    if fmt == "md":
        meta = youtube_meta or {}
        if is_youtube_markdown_meta(meta):
            title, source, kind = _markdown_fields_from_youtube_meta(meta)
        elif job is not None:
            file_meta = file_job_markdown_meta(job)
            title, source, kind = file_meta["title"], file_meta["source"], file_meta["kind"]
        else:
            title = str(meta.get("title") or path.stem or "transcript")
            source = str(meta.get("source") or meta.get("url") or "")
            kind = str(meta.get("kind") or "file")
        write_media_markdown(
            path,
            title=title,
            source=source,
            kind=kind,
            segments=segments,
        )
        return
    write_output(path, segments, fmt)
