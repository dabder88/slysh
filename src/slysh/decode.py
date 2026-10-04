from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from slysh.paths import install_root
from slysh.subprocess_win import subprocess_no_console_kwargs

FFMPEG_MISSING_MESSAGE = "Рядом с программой нет bin\\ffmpeg.exe."
FILE_UNREADABLE_MESSAGE = "Не удалось прочитать файл."
DECODE_FAILED_MESSAGE = (
    "Не удалось декодировать аудио. Проверьте формат файла (webm, mp4, wav, mp3)."
)
# Kept for older tests that match this phrasing.
DECODE_ERROR_MESSAGE = FILE_UNREADABLE_MESSAGE


class DecodeError(Exception):
    """Raised when ffmpeg is missing or the media file cannot be decoded."""


class DecodeCancelledError(DecodeError):
    """Raised when decode is stopped via cancelled()."""


def find_ffmpeg() -> str | None:
    env = os.environ.get("FFMPEG_BINARY") or os.environ.get("FFMPEG_PATH")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return str(candidate)
        bundled = candidate / "ffmpeg.exe" if candidate.is_dir() else None
        if bundled and bundled.is_file():
            return str(bundled)
    local = install_root() / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    which = shutil.which("ffmpeg")
    if which:
        return which
    return None


def _ffmpeg_kwargs() -> dict:
    return subprocess_no_console_kwargs()


def _wait_ffmpeg(
    proc: subprocess.Popen[bytes],
    *,
    cancelled: Callable[[], bool] | None,
    poll_s: float = 0.05,
) -> None:
    while proc.poll() is None:
        if cancelled and cancelled():
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
            raise DecodeCancelledError("Декодирование отменено")
        time.sleep(poll_s)


def _ffmpeg_pcm_cmd(
    ffmpeg: str,
    input_path: str,
    output_path: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[str]:
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    if start_ms is not None and start_ms > 0:
        cmd.extend(["-ss", f"{start_ms / 1000:.3f}"])
    cmd.extend(["-i", input_path])
    if end_ms is not None:
        begin = 0 if start_ms is None else max(0, int(start_ms))
        duration_ms = max(0, int(end_ms) - begin)
        cmd.extend(["-t", f"{duration_ms / 1000:.3f}"])
    cmd.extend(["-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", output_path])
    return cmd


def decode_pcm_16k_mono(
    path: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[np.ndarray, int]:
    """Decode audio/video to 16 kHz mono float32 PCM via ffmpeg.

    Copies the source to a short ASCII temp path first so Windows ffmpeg can
    both open Cyrillic filenames and seek inside webm/mp4 containers.
    Writes PCM to a temp file (not capture_output) so cancel can stop ffmpeg.
    """
    source = Path(path)
    if not source.is_file():
        raise DecodeError(f"{FILE_UNREADABLE_MESSAGE} {path}")

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise DecodeError(FFMPEG_MISSING_MESSAGE)

    suffix = source.suffix if source.suffix else ".bin"
    fd, tmp = tempfile.mkstemp(prefix="gigaam_", suffix=suffix)
    os.close(fd)
    fd_pcm, pcm_path = tempfile.mkstemp(prefix="gigaam_pcm_", suffix=".f32le")
    os.close(fd_pcm)
    try:
        shutil.copyfile(source, tmp)
        cmd = _ffmpeg_pcm_cmd(
            ffmpeg,
            tmp,
            pcm_path,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                **_ffmpeg_kwargs(),
            )
        except FileNotFoundError as exc:
            raise DecodeError(FFMPEG_MISSING_MESSAGE) from exc
        _wait_ffmpeg(proc, cancelled=cancelled)
        if proc.stderr:
            proc.stderr.read()
        if proc.returncode != 0:
            raise DecodeError(DECODE_FAILED_MESSAGE)
        pcm_file = Path(pcm_path)
        if not pcm_file.is_file() or pcm_file.stat().st_size == 0:
            raise DecodeError(DECODE_FAILED_MESSAGE)
        pcm = np.fromfile(pcm_path, dtype=np.float32)
        if pcm.size == 0:
            raise DecodeError(DECODE_FAILED_MESSAGE)
        return pcm, 16000
    finally:
        for p in (tmp, pcm_path):
            try:
                os.remove(p)
            except OSError:
                pass


_DURATION_RE = re.compile(
    r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
STT_MAX_BYTES = 20 * 1024 * 1024
STT_CHUNK_MS = 8 * 60 * 1000
DEFAULT_REMOTE_FILE_CHUNK_MS = 3 * 60 * 1000


def remote_file_chunk_ms() -> int:
    raw = (os.environ.get("GIGAAM_REMOTE_FILE_CHUNK_MS") or "").strip()
    if raw:
        try:
            return max(60_000, int(raw))
        except ValueError:
            pass
    return DEFAULT_REMOTE_FILE_CHUNK_MS


def _copy_media_to_ascii_temp(source: Path) -> str:
    suffix = source.suffix if source.suffix else ".bin"
    fd, tmp = tempfile.mkstemp(prefix="gigaam_", suffix=suffix)
    os.close(fd)
    shutil.copyfile(source, tmp)
    return tmp


def media_duration_ms(path: str) -> int:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise DecodeError(FFMPEG_MISSING_MESSAGE)
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", path, "-f", "null", "-"],
        capture_output=True,
        check=False,
        **_ffmpeg_kwargs(),
    )
    text = (result.stderr or b"").decode("utf-8", errors="replace")
    match = _DURATION_RE.search(text)
    if not match:
        return 0
    hours, minutes, seconds = match.groups()
    total_ms = (int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000
    return max(0, int(total_ms))


def extract_stt_mp3(
    path: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    dest: str | None = None,
) -> str:
    source = Path(path)
    if not source.is_file():
        raise DecodeError(f"{FILE_UNREADABLE_MESSAGE} {path}")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise DecodeError(FFMPEG_MISSING_MESSAGE)
    out = dest
    if not out:
        fd, out = tempfile.mkstemp(prefix="gigaam_stt_", suffix=".mp3")
        os.close(fd)
    tmp = _copy_media_to_ascii_temp(source)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    if start_ms is not None and start_ms > 0:
        cmd.extend(["-ss", f"{start_ms / 1000:.3f}"])
    cmd.extend(["-i", tmp])
    if end_ms is not None:
        begin = 0 if start_ms is None else max(0, start_ms)
        duration_ms = max(0, int(end_ms) - begin)
        cmd.extend(["-t", f"{duration_ms / 1000:.3f}"])
    cmd.extend(["-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", out])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            **_ffmpeg_kwargs(),
        )
    except FileNotFoundError as exc:
        raise DecodeError(FFMPEG_MISSING_MESSAGE) from exc
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if result.returncode != 0 or not Path(out).is_file() or Path(out).stat().st_size == 0:
        try:
            os.remove(out)
        except OSError:
            pass
        raise DecodeError(DECODE_FAILED_MESSAGE)
    return out


def prepare_stt_chunks(
    path: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    *,
    chunk_ms: int | None = None,
) -> list[tuple[str, int, int]]:
    """Return [(mp3_path, offset_ms, duration_ms), ...]; caller deletes paths."""
    split_ms = chunk_ms if chunk_ms is not None else STT_CHUNK_MS
    whole = extract_stt_mp3(path, start_ms=start_ms, end_ms=end_ms)
    size = Path(whole).stat().st_size
    duration = media_duration_ms(whole)
    offset0 = 0 if start_ms is None else max(0, int(start_ms))
    if size <= STT_MAX_BYTES and (duration <= 0 or duration <= split_ms):
        return [(whole, offset0, duration or 1)]
    if duration <= 0:
        return [(whole, offset0, 1)]
    chunks: list[tuple[str, int, int]] = []
    chunk_ms = split_ms
    try:
        pos = 0
        while pos < duration:
            piece_ms = min(chunk_ms, duration - pos)
            fd, dest = tempfile.mkstemp(prefix="gigaam_stt_c_", suffix=".mp3")
            os.close(fd)
            extract_stt_mp3(whole, start_ms=pos, end_ms=pos + piece_ms, dest=dest)
            if Path(dest).stat().st_size > STT_MAX_BYTES and piece_ms > 60_000:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                chunk_ms = max(60_000, piece_ms // 2)
                continue
            chunks.append((dest, offset0 + pos, piece_ms))
            pos += piece_ms
    finally:
        try:
            os.remove(whole)
        except OSError:
            pass
    return chunks
