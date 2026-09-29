from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from slysh.models import Segment
from slysh.http_proxy import subprocess_env_for_target
from slysh.providers import find_gemini_binary
from slysh.remote_asr import RemoteAsrError, parse_transcription_payload

GEMINI_PROMPT = (
    "Transcribe this audio verbatim in the original language. "
    "Output JSON only with keys text and optional segments "
    '[{"start":0.0,"end":1.2,"text":"..."}]. No commentary.'
)


def _ffmpeg_hidden_kwargs() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def parse_gemini_output(raw: str, duration_ms: int) -> list[Segment]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return [Segment(0, max(int(duration_ms), 1), text)]
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [Segment(0, max(int(duration_ms), 1), text)]
    if isinstance(data, dict) and "response" in data:
        inner = data.get("response")
        if isinstance(inner, str):
            return parse_gemini_output(inner, duration_ms)
        if isinstance(inner, dict):
            data = inner
    if isinstance(data, dict):
        segs = parse_transcription_payload(data, duration_ms)
        if segs:
            return segs
    if isinstance(data, str) and data.strip():
        return [Segment(0, max(int(duration_ms), 1), data.strip())]
    return [Segment(0, max(int(duration_ms), 1), text)]


def transcribe_gemini_file(
    audio_path: str,
    duration_ms: int,
    cancelled: Callable[[], bool] | None = None,
    runner=None,
    binary: str | None = None,
    timeout: float = 600,
) -> list[Segment]:
    exe = binary or find_gemini_binary()
    if not exe:
        raise RemoteAsrError(
            "Gemini CLI не найден. Установите @google/gemini-cli и выполните gemini."
        )
    path = Path(audio_path).resolve()
    prompt = f"{GEMINI_PROMPT} @{path}"
    cmd = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
    ]
    run = runner or subprocess.run
    try:
        completed = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=subprocess_env_for_target("gemini"),
            **_ffmpeg_hidden_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RemoteAsrError("Gemini CLI превысил время ожидания.") from exc
    except FileNotFoundError as exc:
        raise RemoteAsrError("Gemini CLI не найден.") from exc
    if cancelled and cancelled():
        return []
    code = int(getattr(completed, "returncode", 1) or 0)
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    if code != 0:
        detail = (stderr or stdout).strip() or f"код {code}"
        logging.info("gemini cli failed: %s", detail[:500])
        raise RemoteAsrError(f"Gemini CLI: {detail[:400]}")
    return parse_gemini_output(stdout, duration_ms)
