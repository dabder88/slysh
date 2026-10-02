from __future__ import annotations

import pytest

import slysh.updates as updates


def _reset_state() -> None:
    with updates._lock:
        updates._state.clear()
        updates._state.update(
            {
                "phase": "idle",
                "error": None,
                "bytes_done": 0,
                "bytes_total": 0,
                "path": None,
                "sha256": None,
                "pending": None,
            }
        )


def test_parse_expected_sha256_from_body():
    digest = "a" * 64
    body = f"Changelog\n\nsha256: {digest}\n"
    assert updates._parse_expected_sha256(body) == digest


def test_start_download_requires_sha256(monkeypatch):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    _reset_state()
    with updates._lock:
        updates._state["pending"] = {
            "version": "9.9.9",
            "download_url": "https://github.com/o/r/releases/download/v9.9.9/Slysh-Setup.exe",
            "size": 1,
            "expected_sha256": None,
        }
    with pytest.raises(ValueError, match="sha256"):
        updates.start_download()


def test_apply_update_requires_matching_digest(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    installer = tmp_path / "Slysh-Setup-1.0.0.exe"
    installer.write_bytes(b"x")
    digest = "a" * 64
    _reset_state()
    with updates._lock:
        updates._state.update(
            {
                "phase": "ready",
                "path": str(installer),
                "sha256": "b" * 64,
                "pending": {"expected_sha256": digest},
            }
        )
    with pytest.raises(ValueError, match="Контрольная сумма"):
        updates.apply_update()
