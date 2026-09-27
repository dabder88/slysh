from http.cookiejar import Cookie
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from slysh.youtube_cookies import (
    YoutubeCookiesError,
    _cookie_db_path,
    extract_cookies,
)


def test_cookie_db_path_firefox_missing(tmp_path):
    profile = tmp_path / "empty.default"
    profile.mkdir()
    with pytest.raises(YoutubeCookiesError, match="нет файла cookies"):
        _cookie_db_path("firefox", profile)


def test_cookie_db_path_firefox_found(tmp_path):
    profile = tmp_path / "user.default-release"
    profile.mkdir()
    cookie_db = profile / "cookies.sqlite"
    cookie_db.write_bytes(b"sqlite")
    assert _cookie_db_path("firefox", profile) == cookie_db


def test_extract_cookies_writes_netscape(tmp_path, monkeypatch):
    profile_dir = tmp_path / "ff.default-release"
    profile_dir.mkdir()
    cookie_db = profile_dir / "cookies.sqlite"
    cookie_db.write_bytes(b"sqlite")

    dest = tmp_path / "youtube" / "cookies.txt"
    meta = tmp_path / "youtube" / "cookies-meta.json"
    monkeypatch.setattr(
        "slysh.youtube_cookies.youtube_cookies_path",
        lambda: dest,
    )
    monkeypatch.setattr(
        "slysh.youtube_cookies.youtube_dir",
        lambda: dest.parent,
    )
    monkeypatch.setattr(
        "slysh.youtube_cookies._meta_path",
        lambda: meta,
    )
    monkeypatch.setattr(
        "slysh.youtube_cookies._resolve_profile_path",
        lambda browser, profile: profile_dir,
    )

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
    monkeypatch.setattr(
        "slysh.youtube_cookies._load_browser_jar",
        lambda browser, cookie_file: jar,
    )

    status = extract_cookies("firefox", "ff.default-release")
    assert status["present"] is True
    assert status["source"] == "extract"
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "youtube.com" in text
    assert "SID" in text


def test_list_browser_profiles_firefox_only(monkeypatch):
    from slysh.youtube_cookies import list_browser_profiles

    monkeypatch.setattr(
        "slysh.youtube_cookies._firefox_profiles",
        lambda: [
            {
                "browser": "firefox",
                "profile": "abc",
                "label": "Firefox — default-release",
                "cookies_available": True,
            }
        ],
    )
    monkeypatch.setattr(
        "slysh.youtube_cookies.browser_cookie3_available",
        lambda: True,
    )
    data = list_browser_profiles()
    assert data["firefox_only"] is True
    assert len(data["profiles"]) == 1
    assert data["profiles"][0]["browser"] == "firefox"


def test_extract_cookies_no_youtube_cookies(tmp_path, monkeypatch):
    profile_dir = tmp_path / "ff.default-release"
    profile_dir.mkdir()
    monkeypatch.setattr(
        "slysh.youtube_cookies._resolve_profile_path",
        lambda browser, profile: profile_dir,
    )
    monkeypatch.setattr(
        "slysh.youtube_cookies._cookie_db_path",
        lambda browser, profile_path: profile_dir / "cookies.sqlite",
    )

    jar = MagicMock()
    jar.__iter__.return_value = iter([])
    monkeypatch.setattr(
        "slysh.youtube_cookies._load_browser_jar",
        lambda browser, cookie_file: jar,
    )

    with pytest.raises(YoutubeCookiesError, match="youtube.com не найдены"):
        extract_cookies("firefox", "ff.default-release")
