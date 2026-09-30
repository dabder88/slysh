"""Smoke: /cancel must not suppress the next /transcribe_chunk (wave A2)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_engine_cancel_sequence: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.engine_server import _CliFakeBackend, _decode_pcm, create_app

    client = TestClient(create_app(_CliFakeBackend(), _decode_pcm))
    client.post("/cancel")
    resp = client.post("/transcribe_chunk", json={"samples": [0.0, 0.1]})
    if resp.status_code != 200:
        return _fail(f"HTTP {resp.status_code}: {resp.text[:200]}")
    segments = resp.json().get("segments") or []
    if not segments:
        return _fail("expected segments after cancel+chunk")
    print("smoke_engine_cancel_sequence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
