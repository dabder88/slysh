# uv sync --extra engine
# then: uv run python scripts/smoke_gigaam.py
"""Smoke-test GigaAMBackend with 3 seconds of silence. Not run by pytest."""

from __future__ import annotations

import numpy as np

from slysh.chunking import SAMPLE_RATE
from slysh.rnnt_backend import GigaAMBackend


def main() -> None:
    pcm = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)
    backend = GigaAMBackend()
    segments = backend.transcribe_chunk(pcm, cancelled=lambda: False)
    print(f"device={backend.device}")
    print(f"segments={len(segments)}")
    for seg in segments:
        print(f"{seg.start_ms}-{seg.end_ms}: {seg.text!r}")


if __name__ == "__main__":
    main()
