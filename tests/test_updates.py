from __future__ import annotations

import json
from pathlib import Path

import pytest

from slysh import updates
from slysh.release_version import installed_app_layout, release_version


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


def test_pick_setup_asset():
    release = {
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://example.com/n"},
            {
                "name": "Slysh-Setup.exe",
                "browser_download_url": "https://objects.githubusercontent.com/x",
                "size": 100,
            },
        ]
    }
    asset = updates._pick_setup_asset(release)
    assert asset["name"] == "Slysh-Setup.exe"


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
                "name": "Slysh-Setup.exe",
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
