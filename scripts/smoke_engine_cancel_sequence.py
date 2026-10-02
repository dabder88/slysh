"""Smoke: engine /cancel does not break the next /transcribe_chunk (A2)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_engine_cancel_sequence: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.engine_server import _decode_pcm, create_app
    from slysh.models import Segment

    class Tracking:
        def __init__(self) -> None:
            self.calls = 0

        def transcribe_chunk(self, pcm, cancelled):
            self.calls += 1
            if cancelled():
                return []
            return [Segment(0, 50, f"seg-{self.calls}")]

    backend = Tracking()
    client = TestClient(create_app(backend, _decode_pcm))
    client.post("/cancel")
    first = client.post("/transcribe_chunk", json={"samples": [0.0]})
    if not first.json().get("segments"):
        return _fail("first chunk empty after prior cancel")
    second = client.post("/transcribe_chunk", json={"samples": [0.0]})
    text = (second.json().get("segments") or [{}])[0].get("text")
    if text != "seg-2":
        return _fail(f"expected seg-2, got {text!r}")
    print("smoke_engine_cancel_sequence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
