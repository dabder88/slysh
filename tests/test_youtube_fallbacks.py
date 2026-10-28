import pytest

from slysh.models import Segment
from slysh.youtube_ingest import YoutubeIngestError, _fetch_ytdlp_with_fallbacks
from slysh.youtube_transcript_api import YoutubeTranscriptApiError
from slysh.youtube_ytdlp import YoutubeYtdlpError


def test_fetch_ytdlp_fallback_to_transcript_api(monkeypatch):
    monkeypatch.setattr("slysh.youtube_ingest.probe_youtube_reachable", lambda **kw: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_ytdlp",
        lambda url, language="ru": (_ for _ in ()).throw(
            YoutubeYtdlpError("yt-dlp fail")
        ),
    )
    monkeypatch.setattr("slysh.youtube_ingest.transcript_api_available", lambda: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_api",
        lambda url, language="ru": {
            "title": "",
            "channel": "",
            "upload_date": "",
            "segments": [Segment(0, 1000, "текст")],
        },
    )
    monkeypatch.setattr("slysh.youtube_ingest.apify_api_key", lambda: "")

    payload = _fetch_ytdlp_with_fallbacks(
        "https://www.youtube.com/watch?v=dagGOOxhRcc",
        "ru",
    )
    assert payload["segments"][0].text == "текст"


def test_fetch_ytdlp_fallback_to_apify(monkeypatch):
    monkeypatch.setattr("slysh.youtube_ingest.probe_youtube_reachable", lambda **kw: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_ytdlp",
        lambda url, language="ru": (_ for _ in ()).throw(
            YoutubeYtdlpError("yt-dlp fail")
        ),
    )
    monkeypatch.setattr("slysh.youtube_ingest.transcript_api_available", lambda: False)
    monkeypatch.setattr("slysh.youtube_ingest.apify_api_key", lambda: "token")
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_apify",
        lambda url, language="ru": {
            "title": "Видео",
            "channel": "Канал",
            "upload_date": "",
            "segments": [Segment(0, 1000, "apify")],
        },
    )

    payload = _fetch_ytdlp_with_fallbacks(
        "https://www.youtube.com/watch?v=dagGOOxhRcc",
        "ru",
    )
    assert payload["segments"][0].text == "apify"


def test_fetch_ytdlp_fallback_transcript_api_when_proxy_active_despite_unreachable(
    monkeypatch,
):
    monkeypatch.setattr("slysh.youtube_ingest.probe_youtube_reachable", lambda **kw: False)
    monkeypatch.setattr(
        "slysh.http_proxy.should_use_proxy_for_target",
        lambda tid: tid == "youtube",
    )
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_ytdlp",
        lambda url, language="ru": (_ for _ in ()).throw(
            YoutubeYtdlpError("yt-dlp fail")
        ),
    )
    monkeypatch.setattr("slysh.youtube_ingest.transcript_api_available", lambda: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_api",
        lambda url, language="ru": {
            "title": "",
            "channel": "",
            "upload_date": "",
            "segments": [Segment(0, 1000, "proxy-fallback")],
        },
    )
    monkeypatch.setattr("slysh.youtube_ingest.apify_api_key", lambda: "")

    payload = _fetch_ytdlp_with_fallbacks(
        "https://www.youtube.com/watch?v=dagGOOxhRcc",
        "ru",
    )
    assert payload["segments"][0].text == "proxy-fallback"


def test_fetch_ytdlp_all_fail_suggests_apify(monkeypatch):
    monkeypatch.setattr("slysh.youtube_ingest.probe_youtube_reachable", lambda **kw: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_ytdlp",
        lambda url, language="ru": (_ for _ in ()).throw(
            YoutubeYtdlpError("PO token")
        ),
    )
    monkeypatch.setattr("slysh.youtube_ingest.transcript_api_available", lambda: True)
    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript_api",
        lambda url, language="ru": (_ for _ in ()).throw(
            YoutubeTranscriptApiError("api fail")
        ),
    )
    monkeypatch.setattr("slysh.youtube_ingest.apify_api_key", lambda: "")

    with pytest.raises(YoutubeIngestError):
        _fetch_ytdlp_with_fallbacks(
            "https://www.youtube.com/watch?v=dagGOOxhRcc",
            "ru",
        )
