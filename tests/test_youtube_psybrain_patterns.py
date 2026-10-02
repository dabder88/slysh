from http.cookiejar import Cookie
from unittest.mock import MagicMock

import pytest

from slysh.vtt import parse_srt
from slysh.youtube_apify import (
    YoutubeApifyError,
    _metadata_from_item,
    _segments_from_item,
    fetch_transcript_apify,
)
from slysh.youtube_cookies import extract_cookies_quick
from slysh.youtube_ytdlp import cookies_auth_mode


def test_parse_srt_basic():
    text = """1
00:00:01,000 --> 00:00:03,500
Первая реплика

2
00:00:04,000 --> 00:00:06,000
Вторая реплика
"""
    segments = parse_srt(text)
    assert len(segments) == 2
    assert segments[0].start_ms == 1000
    assert segments[0].text == "Первая реплика"


def test_segments_from_item_transcript_string():
    segments = _segments_from_item({"transcript": "Привет мир"}, "ru")
    assert len(segments) == 1
    assert segments[0].text == "Привет мир"


def test_segments_from_item_subtitles_srt():
    item = {
        "subtitles": [
            {
                "language": "ru",
                "srt": "1\n00:00:01,000 --> 00:00:02,000\nТекст\n",
            }
        ]
    }
    segments = _segments_from_item(item, "ru")
    assert len(segments) == 1
    assert segments[0].text == "Текст"


def test_fetch_transcript_apify_fallback(monkeypatch):
    calls: list[str] = []

    def fake_call(actor_id, body, token):
        calls.append(actor_id)
        if actor_id.startswith("scrapesage"):
            raise YoutubeApifyError("primary failed")
        return [
            {
                "title": "Видео",
                "channelTitle": "Канал",
                "transcript": "Готовый текст",
            }
        ]

    monkeypatch.setattr("slysh.youtube_apify.apify_api_key", lambda: "token")
    monkeypatch.setattr("slysh.youtube_apify._call_apify_actor", fake_call)

    payload = fetch_transcript_apify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert len(calls) == 2
    assert payload["title"] == "Видео"
    assert payload["segments"][0].text == "Готовый текст"


def test_cookies_auth_mode_file(tmp_path, monkeypatch):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape\n", encoding="utf-8")
    monkeypatch.setattr("slysh.youtube_ytdlp.youtube_cookies_path", lambda: cookies)
    assert cookies_auth_mode() == "file"


def test_cookies_auth_mode_browser(tmp_path, monkeypatch):
    cookies = tmp_path / "missing.txt"
    monkeypatch.setattr("slysh.youtube_ytdlp.youtube_cookies_path", lambda: cookies)
    assert cookies_auth_mode() == "browser"


def test_extract_cookies_quick(tmp_path, monkeypatch):
    dest = tmp_path / "youtube" / "cookies.txt"
    meta = tmp_path / "youtube" / "cookies-meta.json"
    monkeypatch.setattr("slysh.youtube_cookies.youtube_cookies_path", lambda: dest)
    monkeypatch.setattr("slysh.youtube_cookies.youtube_dir", lambda: dest.parent)
    monkeypatch.setattr("slysh.youtube_cookies._meta_path", lambda: meta)

    jar = MagicMock()
    jar.__iter__.return_value = iter(
        [
            Cookie(
                version=0,
                name="SID",
                value="abc",
                port=None,
                port_specified=False,
                domain=".youtube.com",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=9999999999,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        ]
    )

    def fake_firefox(**kwargs):
        assert kwargs.get("domain_name") == "youtube.com"
        return jar

    fake_module = MagicMock()
    fake_module.firefox = fake_firefox
    monkeypatch.setitem(__import__("sys").modules, "browser_cookie3", fake_module)

    status = extract_cookies_quick("firefox")
    assert status["present"] is True
    assert dest.is_file()


def test_metadata_from_item_keeps_video_title_with_chapters():
    meta = _metadata_from_item(
        {
            "title": "Claude Fable 5.1 — разбор",
            "channelName": "AI Прорыв",
            "chapters": [
                {"title": "Вступление", "startMs": 0},
                {"title": "Заключение", "startMs": 1275000},
            ],
        }
    )
    assert meta["title"] == "Claude Fable 5.1 — разбор"
    assert len(meta["chapters"]) == 2
    assert meta["chapters"][-1]["title"] == "Заключение"
