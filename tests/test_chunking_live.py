"""Live/meeting chunk defaults."""

from __future__ import annotations

import pytest

from slysh.chunking import (
    CHUNK_SECONDS,
    LIVE_CHUNK_SAMPLES,
    LIVE_CHUNK_SECONDS,
    SAMPLE_RATE,
    WHISPER_LIVE_CHUNK_SECONDS_DEFAULT,
    live_chunk_samples_for_backend,
    live_chunk_seconds_for_backend,
)


def test_live_chunk_default_matches_file_chunk() -> None:
    assert CHUNK_SECONDS == 20
    assert LIVE_CHUNK_SECONDS == 20.0
    assert LIVE_CHUNK_SAMPLES == SAMPLE_RATE * 20


def test_live_chunk_seconds_gigaam_default() -> None:
    assert live_chunk_seconds_for_backend("gigaam") == 20.0


def test_live_chunk_seconds_whisper_default() -> None:
    assert live_chunk_seconds_for_backend("whisper") == WHISPER_LIVE_CHUNK_SECONDS_DEFAULT


def test_live_chunk_seconds_remote_default() -> None:
    assert live_chunk_seconds_for_backend("openrouter") == 20.0
    assert live_chunk_seconds_for_backend("http") == 20.0


def test_live_chunk_seconds_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_LIVE_CHUNK_SECONDS", "8")
    monkeypatch.setenv("GIGAAM_LIVE_CHUNK_SECONDS", "15")
    assert live_chunk_seconds_for_backend("whisper") == 8.0
    assert live_chunk_seconds_for_backend("gigaam") == 15.0


def test_live_chunk_seconds_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_LIVE_CHUNK_SECONDS", "0.2")
    assert live_chunk_seconds_for_backend("whisper") == 1.0
    monkeypatch.setenv("WHISPER_LIVE_CHUNK_SECONDS", "999")
    assert live_chunk_seconds_for_backend("whisper") == 60.0


def test_live_chunk_samples_for_backend_whisper() -> None:
    sec = live_chunk_seconds_for_backend("whisper")
    assert live_chunk_samples_for_backend("whisper") == int(SAMPLE_RATE * sec)
