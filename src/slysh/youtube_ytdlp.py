from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from slysh.models import Segment
from slysh.paths import youtube_cookies_path
from slysh.vtt import parse_vtt

from slysh.youtube_env import find_ytdlp as _find_ytdlp_resolved
from slysh.youtube_env import resolve_ytdlp_command_prefix, ytdlp_missing_message

YTDLP_MISSING_MESSAGE = (
    "yt-dlp не найден. Установите yt-dlp в PATH или выполните: uv sync --extra youtube"
)
COOKIES_FROM_BROWSER = "firefox"
PO_TOKEN_HINT = (
    " YouTube блокирует субтитры через yt-dlp (нужен PO Token). "
    "Попробуйте метод Apify или обновите yt-dlp."
)

CookieMode = Literal["none", "file", "browser"]

_AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".m4a", ".webm", ".mp4", ".opus", ".ogg", ".aac", ".flac"}
)
_MIN_AUDIO_BYTES = 4096

_SUBTITLE_STRATEGIES: tuple[tuple[CookieMode, str | None, bool], ...] = (
    ("none", "youtube:player_client=android_vr", False),
    ("none", "youtube:player_client=android", False),
    ("none", "youtube:player_client=mweb", False),
    ("file", None, False),
    ("file", "youtube:player_client=default,-web", False),
    ("file", None, True),
    ("browser", None, False),
    ("browser", "youtube:player_client=android_vr", False),
    ("browser", "youtube:player_client=default,-web", False),
)

_METADATA_STRATEGIES: tuple[tuple[CookieMode, str | None], ...] = (
    ("none", None),
    ("none", "youtube:player_client=android_vr"),
    ("none", "youtube:player_client=android"),
    ("none", "youtube:player_client=mweb"),
    ("file", None),
    ("file", "youtube:player_client=default,-web"),
    ("browser", None),
    ("browser", "youtube:player_client=android_vr"),
)

_AUDIO_DOWNLOAD_STRATEGIES: tuple[tuple[CookieMode, str | None], ...] = (
    # Свежие cookies из Firefox обычно надёжнее устаревшего cookies.txt.
    ("browser", None),
    ("browser", "youtube:player_client=android_vr"),
    ("browser", "youtube:player_client=android"),
    ("browser", "youtube:player_client=default,-web"),
    ("file", None),
    ("file", "youtube:player_client=android_vr"),
    ("file", "youtube:player_client=default,-web"),
    ("none", "youtube:player_client=android_vr"),
    ("none", "youtube:player_client=android"),
    ("none", "youtube:player_client=mweb"),
)


class YoutubeYtdlpError(Exception):
    """Raised when yt-dlp subtitle fetch fails."""


def find_ytdlp() -> str | None:
    return _find_ytdlp_resolved()


def cookies_auth_mode() -> str:
    cookies = youtube_cookies_path()
    if cookies.is_file() and cookies.stat().st_size > 0:
        return "file"
    return "browser"


def _js_runtime_args() -> list[str]:
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
    return []


def _strategy_args(cookie_mode: CookieMode, extractor_args: str | None) -> list[str]:
    args = [*_js_runtime_args()]
    if cookie_mode == "file":
        cookies = youtube_cookies_path()
        if cookies.is_file() and cookies.stat().st_size > 0:
            args.extend(["--cookies", str(cookies)])
        else:
            args.extend(["--cookies-from-browser", COOKIES_FROM_BROWSER])
    elif cookie_mode == "browser":
        args.extend(["--cookies-from-browser", COOKIES_FROM_BROWSER])
    if extractor_args:
        args.extend(["--extractor-args", extractor_args])
    return args


def _base_ytdlp_args() -> list[str]:
    return _strategy_args("file", None)


def _subprocess_kwargs() -> dict:
    from slysh.http_proxy import subprocess_env_for_target

    kwargs: dict = {"env": subprocess_env_for_target("youtube")}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _run_ytdlp(
    args: list[str],
    *,
    timeout: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    ytdlp_procs: dict[int, subprocess.Popen] | None = None,
    job_id: int | None = None,
) -> subprocess.CompletedProcess[str]:
    prefix = resolve_ytdlp_command_prefix()
    if not prefix:
        raise YoutubeYtdlpError(ytdlp_missing_message())
    command = [*prefix, *args]

    if cancelled is None:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
                **_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            stderr = ""
            if exc.stderr:
                stderr = (
                    exc.stderr.decode("utf-8", errors="replace")
                    if isinstance(exc.stderr, bytes)
                    else str(exc.stderr)
                )
            message = f"yt-dlp timeout after {timeout}s"
            if stderr:
                message = f"{message}\n{stderr[-400:]}"
            return subprocess.CompletedProcess(command, 124, "", message)

    from slysh.speakers import SpeakerCancelledError

    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
        if ytdlp_procs is not None and job_id is not None:
            ytdlp_procs[job_id] = proc
        deadline = time.monotonic() + timeout if timeout else None
        while proc.poll() is None:
            if cancelled():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise SpeakerCancelledError()
            if deadline is not None and time.monotonic() >= deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return subprocess.CompletedProcess(
                    command,
                    124,
                    "",
                    f"yt-dlp timeout after {timeout}s",
                )
            time.sleep(0.3)
        stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(
            command,
            proc.returncode or 0,
            stdout or "",
            stderr or "",
        )
    finally:
        if ytdlp_procs is not None and job_id is not None:
            ytdlp_procs.pop(job_id, None)


def _lang_rank(name: str, preferred: str) -> tuple[int, str]:
    base = name.lower()
    preferred = preferred.lower()
    parts = base.split(".")
    if base == preferred:
        return (0, base)
    if preferred in parts:
        return (1, base)
    if base.startswith(f"{preferred}-") or base.startswith(f"{preferred}_"):
        return (2, base)
    if preferred == "ru" and "ru" in parts:
        return (2, base)
    if preferred == "en" and "en" in parts:
        return (3, base)
    if ".auto" in base or "auto" in parts:
        return (5, base)
    return (4, base)


def _pick_vtt_file(files: list[Path], preferred: str) -> Path | None:
    vtts = [path for path in files if path.suffix.lower() == ".vtt"]
    if not vtts:
        return None
    return sorted(vtts, key=lambda path: _lang_rank(path.stem, preferred))[0]


def _chapters_from_ytdlp(payload: dict) -> list[dict]:
    chapters: list[dict] = []
    for item in payload.get("chapters") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        start = item.get("start_time")
        if start is None:
            start = item.get("start")
        if start is None or not title:
            continue
        chapters.append(
            {
                "title": title,
                "start_ms": int(float(start) * 1000),
            }
        )
    return chapters


def _metadata_from_json(payload: dict) -> dict:
    title = str(payload.get("title") or "").strip()
    channel = str(payload.get("channel") or payload.get("uploader") or "").strip()
    upload_date = str(payload.get("upload_date") or "").strip()
    if upload_date and re.fullmatch(r"\d{8}", upload_date):
        upload_date = f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    channel_url = str(payload.get("channel_url") or "").strip()
    channel_id = str(payload.get("channel_id") or "").strip()
    if not channel_url and channel_id:
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
    duration_raw = payload.get("duration")
    duration_s = float(duration_raw) if duration_raw is not None else None
    thumbnail_url = str(payload.get("thumbnail") or "").strip()
    return {
        "title": title,
        "channel": channel,
        "channel_url": channel_url,
        "upload_date": upload_date,
        "duration_s": duration_s,
        "chapters": _chapters_from_ytdlp(payload),
        "thumbnail_url": thumbnail_url,
    }


def _stderr_hints(stderr: str) -> str:
    text = stderr or ""
    if "PO token" in text or "PO Token" in text:
        return PO_TOKEN_HINT
    if "Sign in to confirm" in text or "not a bot" in text:
        return " YouTube запросил проверку — войдите в аккаунт в Firefox."
    return ""


def _download_subtitles(
    url: str,
    language: str,
    out_template: str,
    cookie_mode: CookieMode,
    extractor_args: str | None,
    all_langs: bool,
) -> tuple[list[Path], str]:
    sub_langs = "all" if all_langs else (f"{language},en" if language != "en" else "en")
    result = _run_ytdlp(
        [
            *_strategy_args(cookie_mode, extractor_args),
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang",
            sub_langs,
            "--sub-format",
            "vtt",
            "--skip-download",
            "-o",
            out_template,
            url,
        ]
    )
    stderr = (result.stderr or result.stdout or "").strip()
    tmp_dir = Path(out_template).parent
    files = list(tmp_dir.glob("*"))
    return files, stderr


def fetch_video_metadata_ytdlp(url: str) -> dict:
    if not find_ytdlp():
        return {}
    for cookie_mode, extractor_args in _METADATA_STRATEGIES:
        result = _run_ytdlp(
            [
                *_strategy_args(cookie_mode, extractor_args),
                "--dump-json",
                "--skip-download",
                url,
            ]
        )
        if result.returncode != 0:
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("title") or "").strip():
            return _metadata_from_json(payload)
    return {}


def fetch_transcript_ytdlp(url: str, language: str = "ru") -> dict:
    meta_payload: dict = {}
    meta_result = _run_ytdlp([*_base_ytdlp_args(), "--dump-json", "--skip-download", url])
    if meta_result.returncode == 0:
        try:
            parsed = json.loads(meta_result.stdout)
            if isinstance(parsed, dict):
                meta_payload = parsed
        except json.JSONDecodeError:
            pass

    lang = (language or "ru").strip() or "ru"
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="slysh-ytdlp-") as tmp:
        out_template = str(Path(tmp) / "%(id)s")
        for cookie_mode, extractor_args, all_langs in _SUBTITLE_STRATEGIES:
            files, stderr = _download_subtitles(
                url,
                lang,
                out_template,
                cookie_mode=cookie_mode,
                extractor_args=extractor_args,
                all_langs=all_langs,
            )
            vtt_path = _pick_vtt_file(files, lang)
            if vtt_path is None:
                if stderr:
                    errors.append(stderr[-400:])
                continue
            segments: list[Segment] = parse_vtt(
                vtt_path.read_text(encoding="utf-8", errors="replace")
            )
            if not segments:
                errors.append("Файл субтитров пустой.")
                continue
            meta = _metadata_from_json(meta_payload) if meta_payload else {
                "title": "",
                "channel": "",
                "channel_url": "",
                "upload_date": "",
                "duration_s": None,
                "chapters": [],
                "thumbnail_url": "",
            }
            return {
                "title": meta["title"],
                "channel": meta["channel"],
                "channel_url": meta["channel_url"],
                "upload_date": meta["upload_date"],
                "duration_s": meta["duration_s"],
                "chapters": meta["chapters"],
                "thumbnail_url": meta["thumbnail_url"],
                "segments": segments,
            }

    combined = "\n".join(errors)
    hint = _stderr_hints(combined)
    raise YoutubeYtdlpError(
        "Субтитры не найдены для этого видео через yt-dlp."
        + hint
        + (" Попробуйте Apify." if not hint else "")
    )


def _pick_audio_file(directory: Path) -> Path | None:
    candidates = [
        path
        for path in directory.glob("audio.*")
        if is_usable_audio_file(path)
    ]
    if not candidates:
        return None
    preferred = [path for path in candidates if path.suffix.lower() == ".wav"]
    pool = preferred or candidates
    return sorted(pool, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def is_usable_audio_file(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix in {".part", ".ytdl"}:
        return False
    if suffix not in _AUDIO_EXTENSIONS:
        return False
    try:
        return path.stat().st_size >= _MIN_AUDIO_BYTES
    except OSError:
        return False


def _clear_audio_attempt_files(out_dir: Path) -> None:
    for pattern in ("audio.*", "*.part", "*.ytdl"):
        for old_file in out_dir.glob(pattern):
            try:
                old_file.unlink()
            except OSError:
                pass


def download_audio_ytdlp(
    url: str,
    out_dir: Path,
    *,
    cancelled: Callable[[], bool] | None = None,
    ytdlp_procs: dict[int, subprocess.Popen] | None = None,
    job_id: int | None = None,
) -> Path:
    from slysh.speakers import SpeakerCancelledError

    if not find_ytdlp():
        raise YoutubeYtdlpError(YTDLP_MISSING_MESSAGE)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "audio.%(ext)s")
    errors: list[str] = []
    for cookie_mode, extractor_args in _AUDIO_DOWNLOAD_STRATEGIES:
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        _clear_audio_attempt_files(out_dir)
        result = _run_ytdlp(
            [
                *_strategy_args(cookie_mode, extractor_args),
                "--socket-timeout",
                "20",
                "--retries",
                "3",
                "--fragment-retries",
                "5",
                "--no-continue",
                "--force-overwrites",
                "-f",
                "worstaudio/bestaudio/best",
                "-x",
                "--audio-format",
                "wav",
                "--postprocessor-args",
                "ffmpeg:-ar 16000 -ac 1",
                "-o",
                out_template,
                url,
            ],
            timeout=300,
            cancelled=cancelled,
            ytdlp_procs=ytdlp_procs,
            job_id=job_id,
        )
        stderr = (result.stderr or result.stdout or "").strip()
        if stderr:
            errors.append(stderr[-400:])
        if result.returncode == 124:
            errors.append(f"Таймаут скачивания ({cookie_mode}).")
        audio_path = _pick_audio_file(out_dir)
        if audio_path is not None:
            return audio_path
    hint = _stderr_hints("\n".join(errors))
    browser_hint = (
        " Если вы вошли в YouTube в Firefox, нажмите «Извлечь» cookies на экране YouTube "
        "или закройте Firefox и повторите — Slysh также пробует cookies напрямую из браузера."
    )
    raise YoutubeYtdlpError(
        "Не удалось скачать аудио для определения спикеров через yt-dlp."
        + hint
        + (
            browser_hint
            if "проверку" in hint or "Sign in" in "\n".join(errors)
            else ""
        )
        + (" Проверьте cookies или yt-dlp." if not hint else "")
    )
