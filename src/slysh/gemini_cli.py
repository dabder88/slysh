from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from slysh.models import Segment
from slysh.http_proxy import subprocess_env_for_target
from slysh.providers import find_gemini_binary
from slysh.remote_asr import RemoteAsrError, parse_transcription_payload

# §5.1 Slysh contract: temp cwd, copy media as fixed basename, prompt uses @basename only;
# _assert_safe_gemini_cmd blocks yolo/tools/abs paths (see ci/check_gemini_cli_prompt.py).

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


_DISALLOWED_GEMINI_CMD_MARKERS = (
    "yolo",
    "--approval-mode",
    "--allowed-tools",
    "--include-directories",
)


def _assert_safe_gemini_cmd(cmd: list[str]) -> None:
    flat = " ".join(str(part) for part in cmd).lower()
    for marker in _DISALLOWED_GEMINI_CMD_MARKERS:
        if marker in flat:
            raise RemoteAsrError(
                "Gemini CLI: недопустимый аргумент (ограниченный режим Slysh)."
            )
    for part in cmd:
        text = str(part)
        for ref in re.findall(r"@([^\s\"']+)", text):
            if "/" in ref or "\\" in ref or ":" in ref or ref.startswith("."):
                raise RemoteAsrError(
                    "Gemini CLI: допускается только @имя_файла в рабочей папке."
                )


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


def _run_gemini_subprocess(
    cmd: list[str],
    *,
    cwd: str,
    timeout: float,
    cancelled: Callable[[], bool] | None,
    runner,
) -> subprocess.CompletedProcess | None:
    env = subprocess_env_for_target("gemini")
    hidden = _ffmpeg_hidden_kwargs()
    if runner is not None:
        return runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
            cwd=cwd,
            **hidden,
        )
    deadline = time.monotonic() + max(float(timeout), 1.0)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        **hidden,
    )
    try:
        while proc.poll() is None:
            if cancelled and cancelled():
                proc.kill()
                proc.wait(timeout=5)
                return None
            if time.monotonic() >= deadline:
                proc.kill()
                proc.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd, timeout)
            time.sleep(0.15)
        stdout, stderr = proc.communicate(timeout=1)
        return subprocess.CompletedProcess(
            cmd,
            proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        if proc.poll() is None:
            proc.kill()


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
    if cancelled and cancelled():
        return []
    src = Path(audio_path).resolve()
    if not src.is_file():
        raise RemoteAsrError("Gemini CLI: аудиофайл не найден.")
    with tempfile.TemporaryDirectory(prefix="slysh-gemini-") as tmp:
        work = Path(tmp)
        dest = work / f"audio{src.suffix or '.wav'}"
        shutil.copy2(src, dest)
        prompt = f"{GEMINI_PROMPT} @{dest.name}"
        cmd = [
            exe,
            "-p",
            prompt,
            "--output-format",
            "json",
        ]
        _assert_safe_gemini_cmd(cmd)
        try:
            completed = _run_gemini_subprocess(
                cmd,
                cwd=str(work),
                timeout=timeout,
                cancelled=cancelled,
                runner=runner,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteAsrError("Gemini CLI превысил время ожидания.") from exc
        except FileNotFoundError as exc:
            raise RemoteAsrError("Gemini CLI не найден.") from exc
    if completed is None:
        return []
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
