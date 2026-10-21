"""Resolve Python / yt-dlp for YouTube extras (UI .venv vs .venv-engine)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

_MODULE_IMPORT = {
    "yt_dlp": "yt_dlp",
    "browser_cookie3": "browser_cookie3",
    "youtube_transcript_api": "youtube_transcript_api",
}


def python_has_module(exe: str, module: str) -> bool:
    import_name = _MODULE_IMPORT.get(module, module.replace("-", "_"))
    try:
        proc = subprocess.run(
            [exe, "-c", f"import {import_name}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def youtube_python_candidates() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        key = candidate.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(candidate)

    add(sys.executable)
    try:
        from slysh.runtime_env import resolve_engine_subprocess_python, use_split_engine_venv

        if use_split_engine_venv():
            from slysh.runtime_setup import engine_packages_ok

            if engine_packages_ok():
                add(resolve_engine_subprocess_python())
    except Exception:
        logging.debug("engine python candidate skipped", exc_info=True)
    return ordered


def resolve_youtube_python(*, require: str | None = None) -> str | None:
    module = require or "yt_dlp"
    for exe in youtube_python_candidates():
        if python_has_module(exe, module):
            return exe
    return None


def ytdlp_missing_message() -> str:
    try:
        from slysh.runtime_setup import engine_packages_ok

        if not engine_packages_ok():
            return (
                "yt-dlp не найден. Сначала установите локальные пакеты расшифровки "
                "(first-run «Локально») или выберите способ Apify на экране YouTube."
            )
    except Exception:
        logging.debug("engine_packages_ok check skipped", exc_info=True)
    return (
        "yt-dlp не найден в окружении engine. Переустановите пакеты в Настройках "
        "или выполните: uv sync --extra engine --extra diarization --extra youtube"
    )


def resolve_ytdlp_command_prefix() -> list[str] | None:
    env = os.environ.get("YTDLP_BINARY") or os.environ.get("YT_DLP_BINARY")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return [str(candidate)]
    which = shutil.which("yt-dlp")
    if which:
        return [which]
    py = resolve_youtube_python(require="yt_dlp")
    if py:
        return [py, "-m", "yt_dlp"]
    return None


def find_ytdlp() -> str | None:
    """Legacy string for status; prefer resolve_ytdlp_command_prefix in subprocess code."""
    prefix = resolve_ytdlp_command_prefix()
    if not prefix:
        return None
    if len(prefix) == 1:
        return prefix[0]
    return f"{prefix[0]} -m yt_dlp"
