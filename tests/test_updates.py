from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from pathlib import Path

import pytest

from slysh import updates
from slysh.release_version import installed_app_layout, release_version


def test_default_marketing_urls():
    assert (
        updates.default_about_url("ru")
        == "https://slyshai.pro/?utm_source=soft&utm_medium=ru"
    )
    assert (
        updates.default_about_url("en")
        == "https://slyshai.pro/en/?utm_source=soft&utm_medium=en"
    )
    assert (
        updates.default_support_url("ru")
        == "https://slyshai.pro/?utm_source=soft&utm_medium=ru#support"
    )
    assert (
        updates.default_support_url("en")
        == "https://slyshai.pro/en/?utm_source=soft&utm_medium=en#support"
    )


def test_app_info_marketing_urls_follow_ui_locale(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    from slysh.ui_locale import save_ui_locale

    save_ui_locale("en")
    info = updates.app_info()
    assert info["about_url"] == updates.default_about_url("en")
    assert info["support_url"] == updates.default_support_url("en")
    save_ui_locale("ru")
    info = updates.app_info()
    assert info["about_url"] == updates.default_about_url("ru")
    assert info["support_url"] == updates.default_support_url("ru")


def test_app_info_marketing_urls_use_ui_locale_hint(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    from slysh.ui_locale import save_ui_locale

    save_ui_locale("en")
    info = updates.app_info(ui_locale_hint="ru")
    assert info["about_url"] == updates.default_about_url("ru")
    assert info["support_url"] == updates.default_support_url("ru")
    save_ui_locale("ru")
    info = updates.app_info(ui_locale_hint="en")
    assert info["about_url"] == updates.default_about_url("en")
    assert info["support_url"] == updates.default_support_url("en")


def test_get_app_info_query_ui_locale(monkeypatch, tmp_path: Path):
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.ui_locale import save_ui_locale

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    save_ui_locale("en")
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db, engine=None))
    r = client.get("/api/app/info", params={"ui_locale": "ru"})
    assert r.status_code == 200
    body = r.json()
    assert body["about_url"] == updates.default_about_url("ru")
    assert body["support_url"] == updates.default_support_url("ru")


def test_version_greater():
    assert updates.version_greater("0.2.0", "0.1.0")
    assert not updates.version_greater("0.1.0", "0.2.0")
    assert not updates.version_greater("1.0.0", "1.0.0")
    assert updates.version_greater("v1.0.1", "1.0.0")


def test_parse_release_version():
    assert updates._parse_release_version("v0.2.0") == "0.2.0"
    assert updates._parse_release_version("1.3.4") == "1.3.4"


def test_parse_expected_sha256():
    body = "Changelog\n\nsha256: abcd0123456789abcdef0123456789abcdef0123456789abcdef0123456789ab\n"
    assert (
        updates._parse_expected_sha256(body)
        == "abcd0123456789abcdef0123456789abcdef0123456789abcdef0123456789ab"
    )


def test_versioned_setup_asset_name():
    assert updates.versioned_setup_asset_name("ru", "1.0.0") == "Slysh-Setup-1.0.0-ru.exe"
    assert updates.versioned_setup_asset_name("en", "v2.3.4") == "Slysh-Setup-2.3.4-en.exe"


def test_pick_setup_asset():
    release = {
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://example.com/n"},
            {
                "name": "Slysh-Setup-ru.exe",
                "browser_download_url": "https://objects.githubusercontent.com/x",
                "size": 100,
            },
        ]
    }
    asset = updates._pick_setup_asset(release)
    assert asset["name"] == "Slysh-Setup-ru.exe"


def test_pick_setup_asset_prefers_versioned_name(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    from slysh.ui_locale import save_ui_locale

    save_ui_locale("ru")
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "Slysh-Setup-1.0.0-ru.exe",
                "browser_download_url": "https://objects.githubusercontent.com/v",
                "size": 100,
            },
            {
                "name": "Slysh-Setup-ru.exe",
                "browser_download_url": "https://objects.githubusercontent.com/x",
                "size": 100,
            },
        ],
    }
    asset = updates._pick_setup_asset(release)
    assert asset["name"] == "Slysh-Setup-1.0.0-ru.exe"


def test_installed_layout_detection(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    installed_app_layout.cache_clear()
    assert not installed_app_layout()
    (tmp_path / "Slysh.exe").write_bytes(b"x")
    (tmp_path / "runtime" / "python").mkdir(parents=True)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "uv.exe").write_bytes(b"x")
    installed_app_layout.cache_clear()
    assert installed_app_layout()


def test_release_version_from_version_json(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    installed_app_layout.cache_clear()
    (tmp_path / "version.json").write_text(
        json.dumps({"version": "0.9.1"}), encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
    assert release_version() == "0.9.1"


def test_check_for_updates_mock(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    installed_app_layout.cache_clear()
    (tmp_path / "Slysh.exe").write_bytes(b"x")
    (tmp_path / "runtime" / "python").mkdir(parents=True)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "uv.exe").write_bytes(b"x")
    (tmp_path / "version.json").write_text(
        json.dumps({"version": "0.1.0", "github_repo": "acme/slysh"}),
        encoding="utf-8",
    )

    payload = {
        "tag_name": "v0.2.0",
        "body": "Notes",
        "html_url": "https://github.com/acme/slysh/releases/tag/v0.2.0",
        "assets": [
            {
                "name": "Slysh-Setup-ru.exe",
                "browser_download_url": "https://objects.githubusercontent.com/setup.exe",
                "size": 50,
            }
        ],
    }

    def fake_json(_url: str) -> dict:
        return payload

    monkeypatch.setattr(updates, "_http_json", fake_json)
    result = updates.check_for_updates()
    assert result["has_update"] is True
    assert result["latest_version"] == "0.2.0"


def test_updates_enabled_requires_layout(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    updates.installed_app_layout.cache_clear()
    assert not updates.updates_enabled()


def _sha256_line() -> str:
    return "a" * 64


def test_start_download_repeat_no_deadlock(monkeypatch, tmp_path: Path):
    """Regression: repeated start_download must return while download runs (updates_repeat_deadlock)."""
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    installed_app_layout.cache_clear()
    (tmp_path / "Slysh.exe").write_bytes(b"x")
    (tmp_path / "runtime" / "python").mkdir(parents=True)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "uv.exe").write_bytes(b"x")
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)

    pending = {
        "version": "0.2.0",
        "download_url": "https://objects.githubusercontent.com/setup.exe",
        "size": 100,
        "expected_sha256": _sha256_line(),
    }
    with updates._lock:
        updates._state["pending"] = pending
        updates._state["phase"] = "idle"
        updates._state["error"] = None
        updates._state["path"] = None

    def slow_download(_pending: dict, _operation_id: str) -> None:
        time.sleep(0.5)
        with updates._lock:
            updates._state["phase"] = "ready"
            updates._state["path"] = str(tmp_path / "setup.exe")

    monkeypatch.setattr(updates, "_run_download", slow_download)

    def call_start() -> dict:
        return updates.start_download()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(call_start) for _ in range(3)]
        for fut in concurrent.futures.as_completed(futs, timeout=2.0):
            body = fut.result()
            assert body["phase"] in ("downloading", "ready")

    with updates._lock:
        updates._state["phase"] = "idle"
        updates._state["pending"] = None
