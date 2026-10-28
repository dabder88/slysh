from __future__ import annotations

import json
import subprocess
import sys
from http.cookiejar import MozillaCookieJar

from slysh.models import Segment
from slysh.paths import youtube_cookies_path
from slysh.youtube_env import resolve_youtube_python
from slysh.youtube_errors import format_youtube_failure, parse_subprocess_error_json

YTA_MISSING_MESSAGE = (
    "Пакет youtube-transcript-api не установлен. Выполните: uv pip install youtube-transcript-api"
)


class YoutubeTranscriptApiError(Exception):
    """Raised when youtube-transcript-api cannot fetch a transcript."""


def transcript_api_available() -> bool:
    return resolve_youtube_python(require="youtube_transcript_api") is not None


def _session_with_cookies():
    import requests

    from slysh.http_proxy import requests_proxies_for_target

    path = youtube_cookies_path()
    session = requests.Session()
    session.proxies.update(requests_proxies_for_target("youtube"))
    if not path.is_file() or path.stat().st_size == 0:
        return session
    jar = MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except OSError as exc:
        raise YoutubeTranscriptApiError(f"Не удалось прочитать cookies.txt: {exc}") from exc
    for cookie in jar:
        session.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
    return session


def _snippet_fields(row) -> tuple[str, float, float] | None:
    if isinstance(row, dict):
        text = str(row.get("text") or "").strip()
        start_s = row.get("start")
        duration_s = row.get("duration")
    else:
        text = str(getattr(row, "text", "") or "").strip()
        start_s = getattr(row, "start", None)
        duration_s = getattr(row, "duration", None)
    if not text:
        return None
    try:
        start = float(start_s or 0)
        duration = float(duration_s or 0)
    except (TypeError, ValueError):
        start = 0.0
        duration = 1.0
    return text, start, duration


def _segments_from_snippets(snippets) -> list[Segment]:
    segments: list[Segment] = []
    for row in snippets:
        fields = _snippet_fields(row)
        if fields is None:
            continue
        text, start_s, duration_s = fields
        start_ms = int(start_s * 1000)
        end_ms = int((start_s + duration_s) * 1000)
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
    return segments


def _raise_transcript_api_error(exc: Exception) -> None:
    formatted = format_youtube_failure(exc, method="ytdlp")
    raise YoutubeTranscriptApiError(formatted["message"]) from exc


def _fetch_snippets(api, video_id: str, preferred: list[str]):
    try:
        return api.fetch(video_id, languages=preferred)
    except Exception:
        pass
    try:
        transcript_list = api.list(video_id)
    except Exception as exc:
        _raise_transcript_api_error(exc)
    try:
        transcript = transcript_list.find_transcript(preferred)
    except Exception:
        try:
            transcript = next(iter(transcript_list))
        except StopIteration as exc:
            raise YoutubeTranscriptApiError(
                "Субтитры для этого видео не найдены."
            ) from exc
    try:
        return transcript.fetch()
    except Exception as exc:
        _raise_transcript_api_error(exc)


def _segments_to_json(segments: list[Segment]) -> list[dict]:
    return [
        {
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "text": segment.text,
            "speaker": segment.speaker,
        }
        for segment in segments
    ]


def _payload_from_json(data: dict) -> dict:
    segments = [
        Segment(
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=str(row["text"]),
            speaker=row.get("speaker"),
        )
        for row in data.get("segments") or []
    ]
    return {
        "title": data.get("title") or "",
        "channel": data.get("channel") or "",
        "channel_url": data.get("channel_url") or "",
        "upload_date": data.get("upload_date") or "",
        "duration_s": data.get("duration_s"),
        "chapters": data.get("chapters") or [],
        "thumbnail_url": data.get("thumbnail_url") or "",
        "segments": segments,
    }


def _fetch_transcript_api_inprocess(url: str, language: str = "ru") -> dict:
    from slysh.youtube_ingest import extract_video_id

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise YoutubeTranscriptApiError(YTA_MISSING_MESSAGE) from exc

    video_id = extract_video_id(url)
    if not video_id:
        raise YoutubeTranscriptApiError("Некорректная ссылка YouTube.")

    lang = (language or "ru").strip() or "ru"
    preferred = [lang]
    if lang != "en":
        preferred.append("en")
    session = _session_with_cookies()
    api = YouTubeTranscriptApi(http_client=session)
    snippets = _fetch_snippets(api, video_id, preferred)

    segments = _segments_from_snippets(snippets)
    if not segments:
        raise YoutubeTranscriptApiError("Субтитры пустые.")

    return {
        "title": "",
        "channel": "",
        "channel_url": "",
        "upload_date": "",
        "duration_s": None,
        "chapters": [],
        "thumbnail_url": "",
        "segments": segments,
    }


def _fetch_transcript_api_subprocess(python_exe: str, url: str, language: str) -> dict:
    proc = subprocess.run(
        [
            python_exe,
            "-m",
            "slysh.youtube_transcript_api",
            "fetch",
            "--url",
            url,
            "--language",
            language or "ru",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        parsed = parse_subprocess_error_json(proc.stderr or "")
        if parsed:
            raise YoutubeTranscriptApiError(parsed)
        raw = (proc.stderr or proc.stdout or "youtube-transcript-api subprocess failed").strip()
        message = format_youtube_failure(raw, method="ytdlp")["message"]
        raise YoutubeTranscriptApiError(message)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise YoutubeTranscriptApiError(
            "Некорректный ответ subprocess youtube-transcript-api."
        ) from exc
    return _payload_from_json(payload)


def fetch_transcript_api(url: str, language: str = "ru") -> dict:
    py = resolve_youtube_python(require="youtube_transcript_api")
    if not py:
        raise YoutubeTranscriptApiError(YTA_MISSING_MESSAGE)
    if py == sys.executable:
        return _fetch_transcript_api_inprocess(url, language=language)
    return _fetch_transcript_api_subprocess(py, url, language)


def _cli_fetch(url: str, language: str) -> None:
    try:
        result = _fetch_transcript_api_inprocess(url, language=language)
    except YoutubeTranscriptApiError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        message = format_youtube_failure(exc, method="ytdlp")["message"]
        print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
    out = {**result, "segments": _segments_to_json(result["segments"])}
    print(json.dumps(out, ensure_ascii=False))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="slysh.youtube_transcript_api")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("--url", required=True)
    fetch_parser.add_argument("--language", default="ru")
    args = parser.parse_args()
    if args.cmd == "fetch":
        _cli_fetch(args.url, args.language)


if __name__ == "__main__":
    main()
