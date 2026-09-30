"""Safe media paths for job playback (wave D)."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from slysh.source_path import require_existing_file


def resolve_job_media_path(source_path: str) -> Path:
    raw = (source_path or "").strip()
    if raw.lower().startswith(("http://", "https://", "file:")):
        raise HTTPException(status_code=404, detail="media not found")
    try:
        return require_existing_file(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail="media not found") from None
