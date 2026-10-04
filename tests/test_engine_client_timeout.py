from __future__ import annotations

import json

from slysh.engine_client import (
    ENGINE_CONNECT_TIMEOUT_S,
    ENGINE_CONTROL_TIMEOUT_S,
    ENGINE_TRANSCRIBE_TIMEOUT_S,
    cancel,
    health,
    transcribe_chunk,
)


def test_cancel_uses_control_timeout(monkeypatch):
    seen: list[float | None] = []

    def fake_urlopen(req, timeout=None):
        seen.append(timeout)
        return type(
            "R",
            (),
            {
                "read": lambda self: json.dumps({}).encode(),
                "__enter__": lambda self: self,
                "__exit__": lambda *a: None,
            },
        )()

    monkeypatch.setattr("slysh.engine_client.urlopen", fake_urlopen)
    cancel("http://127.0.0.1:9")
    assert seen == [ENGINE_CONTROL_TIMEOUT_S]


def test_health_uses_connect_timeout(monkeypatch):
    seen: list[float | None] = []

    def fake_urlopen(req, timeout=None):
        seen.append(timeout)
        return type(
            "R",
            (),
            {
                "read": lambda self: json.dumps({"ok": True}).encode(),
                "__enter__": lambda self: self,
                "__exit__": lambda *a: None,
            },
        )()

    monkeypatch.setattr("slysh.engine_client.urlopen", fake_urlopen)
    health("http://127.0.0.1:9")
    assert seen == [ENGINE_CONNECT_TIMEOUT_S]


def test_transcribe_chunk_uses_transcribe_timeout(monkeypatch):
    seen: list[float | None] = []

    def fake_urlopen(req, timeout=None):
        seen.append(timeout)
        return type(
            "R",
            (),
            {
                "read": lambda self: json.dumps({"segments": []}).encode(),
                "__enter__": lambda self: self,
                "__exit__": lambda *a: None,
            },
        )()

    monkeypatch.setattr("slysh.engine_client.urlopen", fake_urlopen)
    transcribe_chunk("http://127.0.0.1:9", [0.0, 0.1])
    assert seen == [ENGINE_TRANSCRIBE_TIMEOUT_S]
