"""Live/meeting chunk defaults."""

from __future__ import annotations

from slysh.chunking import CHUNK_SECONDS, LIVE_CHUNK_SECONDS, LIVE_CHUNK_SAMPLES, SAMPLE_RATE


def test_live_chunk_default_matches_file_chunk() -> None:
    assert CHUNK_SECONDS == 20
    assert LIVE_CHUNK_SECONDS == 20.0
    assert LIVE_CHUNK_SAMPLES == SAMPLE_RATE * 20
