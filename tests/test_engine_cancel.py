"""Engine cancel scope (wave A2): /cancel must not empty the next /transcribe_chunk."""
from __future__ import annotations

from fastapi.testclient import TestClient

from slysh.engine_server import _CliFakeBackend, _decode_pcm, create_app
from slysh.models import Segment


def test_cancel_then_chunk_returns_segments():
    client = TestClient(create_app(_CliFakeBackend(), _decode_pcm))
    client.post("/cancel")
    resp = client.post("/transcribe_chunk", json={"samples": [0.0, 0.1, 0.2]})
    assert resp.status_code == 200
    assert len(resp.json()["segments"]) == 1


def test_cancel_sequence_active_chunk_then_fresh_chunk():
    class TrackingFake:
        def __init__(self) -> None:
            self.calls = 0

        def transcribe_chunk(self, pcm, cancelled):
            self.calls += 1
            if cancelled():
                return []
            return [Segment(0, 50, f"seg-{self.calls}")]

    backend = TrackingFake()
    client = TestClient(create_app(backend, _decode_pcm))
    client.post("/cancel")
    first = client.post("/transcribe_chunk", json={"samples": [0.0]})
    assert first.json()["segments"]
    second = client.post("/transcribe_chunk", json={"samples": [0.0]})
    body = second.json()
    assert body["segments"]
    assert body["segments"][0]["text"] == "seg-2"
