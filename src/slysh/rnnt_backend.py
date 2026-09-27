from __future__ import annotations

import argparse
import os
from typing import Callable

from slysh.models import Segment
from slysh.paths import gigaam_download_root


def resolve_device() -> str:
    if os.getenv("GIGAAM_FORCE_CPU", "").lower() in {"1", "true", "yes"}:
        return "cpu"
    if os.getenv("GIGAAM_DEVICE", "").strip().lower() == "cpu":
        return "cpu"
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class GigaAMBackend:
    def __init__(self) -> None:
        self.device = resolve_device()
        import gigaam

        self._model = gigaam.load_model(
            "e2e_rnnt",
            download_root=str(gigaam_download_root()),
            device=self.device,
        )

    def transcribe_chunk(self, pcm, cancelled: Callable[[], bool]) -> list[Segment]:
        if cancelled():
            return []
        import tempfile

        import soundfile as sf

        from slysh.chunking import SAMPLE_RATE

        if cancelled():
            return []
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        try:
            sf.write(tmp, pcm, SAMPLE_RATE)
            result = self._model.transcribe(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        text = (getattr(result, "text", None) or str(result) or "").strip()
        if not text:
            return []
        dur_ms = int(len(pcm) / SAMPLE_RATE * 1000)
        return [Segment(0, dur_ms, text)]


def load_backend() -> GigaAMBackend:
    return GigaAMBackend()


def download_only() -> None:
    device = resolve_device()
    import gigaam

    gigaam.load_model(
        "e2e_rnnt",
        download_root=str(gigaam_download_root()),
        device=device,
    )
    print("done", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="GigaAM backend helpers")
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download e2e_rnnt weights and exit",
    )
    args = parser.parse_args(argv)
    if args.download_only:
        download_only()
        return
    parser.error("specify --download-only")


if __name__ == "__main__":
    main()
