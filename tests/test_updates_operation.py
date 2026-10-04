from __future__ import annotations

import hashlib
import threading
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
                "operation_id": None,
            }
        )


def _pending_with_sha(content: bytes) -> dict:
    digest = hashlib.sha256(content).hexdigest()
    return {
        "version": "2.0.0",
        "download_url": "https://github.com/o/r/releases/download/v2.0.0/Slysh-Setup.exe",
        "size": len(content),
        "expected_sha256": digest,
    }


def test_stale_download_thread_does_not_mark_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    monkeypatch.setattr(updates, "_download_dir", lambda: tmp_path)
    content = b"installer-bytes"
    pending = _pending_with_sha(content)
    gate = threading.Event()

    class FakeResp:
        def __init__(self) -> None:
            self.headers = {"Content-Length": str(len(content))}

        def read(self, n: int = -1) -> bytes:
            gate.wait(timeout=2.0)
            return content

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    _reset_state()
    with updates._lock:
        updates._state["pending"] = pending
        updates._state["phase"] = "downloading"
        updates._state["operation_id"] = "current-op"

    worker = threading.Thread(
        target=updates._run_download,
        args=(pending, "stale-op"),
        daemon=True,
    )
    worker.start()
    gate.set()
    worker.join(timeout=3.0)
    assert not worker.is_alive()

    with updates._lock:
        assert updates._state["operation_id"] == "current-op"
        assert updates._state["phase"] == "downloading"
        assert updates._state.get("path") is None


def test_check_during_download_preserves_phase(monkeypatch):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    _reset_state()
    with updates._lock:
        updates._state.update(
            {
                "phase": "downloading",
                "bytes_done": 42,
                "bytes_total": 100,
                "operation_id": "abc",
                "pending": {"version": "1.0.0"},
            }
        )

    release = {
        "tag_name": "v2.0.0",
        "body": f"sha256: {'c' * 64}",
        "html_url": "https://github.com/o/r/releases/tag/v2.0.0",
        "assets": [
            {
                "name": updates.SETUP_ASSET_NAME,
                "browser_download_url": "https://github.com/o/r/releases/download/v2.0.0/Slysh-Setup.exe",
                "size": 9,
            }
        ],
    }
    monkeypatch.setattr(updates, "_http_json", lambda _url: release)
    monkeypatch.setattr(updates, "release_version", lambda: "0.1.0")
    monkeypatch.setattr(updates, "_save_last_check", lambda: None)

    updates.check_for_updates()
    with updates._lock:
        assert updates._state["phase"] == "downloading"
        assert updates._state["bytes_done"] == 42
        assert updates._state["pending"]["version"] == "2.0.0"


def test_apply_update_rehashes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "updates_enabled", lambda: True)
    content = b"good"
    digest = hashlib.sha256(content).hexdigest()
    installer = tmp_path / "setup.exe"
    installer.write_bytes(content)
    _reset_state()
    with updates._lock:
        updates._state.update(
            {
                "phase": "ready",
                "path": str(installer),
                "sha256": digest,
                "pending": {"expected_sha256": digest},
            }
        )

    launched: list[list[str]] = []

    def fake_popen(args, **kwargs):
        launched.append(list(args))
        return None

    monkeypatch.setattr(updates.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(updates, "mark_app_update_pending", lambda: None)

    result = updates.apply_update()
    assert result["ok"] is True
    assert launched and str(installer) in launched[0][0]

    installer.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Контрольная сумма"):
        updates.apply_update()
