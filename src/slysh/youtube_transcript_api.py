from __future__ import annotations

from http.cookiejar import MozillaCookieJar

from slysh.models import Segment
from slysh.paths import youtube_cookies_path

YTA_MISSING_MESSAGE = (
    "Пакет youtube-transcript-api не установлен. Выполните: uv pip install youtube-transcript-api"
)


class YoutubeTranscriptApiError(Exception):
    """Raised when youtube-transcript-api cannot fetch a transcript."""


def transcript_api_available() -> bool:
    try:
        import youtube_transcript_api  # noqa: F401
    except ImportError:
        return False
    return True


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


def _fetch_snippets(api, video_id: str, preferred: list[str]):
    try:
        return api.fetch(video_id, languages=preferred)
    except Exception:
        pass
    try:
        transcript_list = api.list(video_id)
    except Exception as exc:
        raise YoutubeTranscriptApiError(
            f"Не удалось получить список субтитров: {exc}"
        ) from exc
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
        raise YoutubeTranscriptApiError(
            f"Не удалось скачать субтитры: {exc}"
        ) from exc


def fetch_transcript_api(url: str, language: str = "ru") -> dict:
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
