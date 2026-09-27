from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import numpy as np

from slysh.chunking import SAMPLE_RATE
from slysh.models import Segment


def resolve_whisper_device() -> tuple[str, str]:
    if os.getenv("GIGAAM_FORCE_CPU", "").lower() in {"1", "true", "yes"}:
        return "cpu", "int8"
    if os.getenv("GIGAAM_DEVICE", "").strip().lower() == "cpu":
        return "cpu", "int8"
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class FasterWhisperBackend:
    def __init__(self, model_path: str) -> None:
        if not model_path:
            raise RuntimeError("Не указан путь к Faster Whisper")
        device, compute_type = resolve_whisper_device()
        self.device = device
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_path, device=device, compute_type=compute_type)

    def transcribe_chunk(self, pcm, cancelled: Callable[[], bool]) -> list[Segment]:
        if cancelled():
            return []
        audio = np.asarray(pcm, dtype=np.float32).reshape(-1)
        return self._decode_audio(audio, cancelled, total_s=len(audio) / SAMPLE_RATE)

    def transcribe_file(
        self,
        pcm,
        cancelled: Callable[[], bool],
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Segment]:
        if cancelled():
            return []
        audio = np.asarray(pcm, dtype=np.float32).reshape(-1)
        total_s = max(len(audio) / SAMPLE_RATE, 0.001)

        def progress(value: float) -> None:
            if on_progress is not None:
                on_progress(value)

        return self._decode_audio(audio, cancelled, total_s=total_s, on_progress=progress)

    def _decode_audio(
        self,
        audio: np.ndarray,
        cancelled: Callable[[], bool],
        *,
        total_s: float,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Segment]:
        if cancelled():
            return []
        segments_iter, _info = self._model.transcribe(audio, language=None)
        segs: list[Segment] = []
        for item in segments_iter:
            if cancelled():
                return segs
            text = (item.text or "").strip()
            if not text:
                continue
            start_ms = int(max(0.0, float(item.start or 0.0)) * 1000)
            end_ms = int(max(float(item.end or 0.0), float(item.start or 0.0)) * 1000)
            segs.append(Segment(start_ms, end_ms, text))
            if on_progress is not None and total_s:
                on_progress(min(1.0, float(item.end or 0.0) / total_s))
        if on_progress is not None:
            on_progress(1.0)
        return segs


class OpenAIWhisperBackend:
    def __init__(self, model_path: str) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise RuntimeError(f"Нет файла Whisper: {model_path}")
        device, _compute = resolve_whisper_device()
        self.device = device
        import whisper

        self._model = whisper.load_model(str(path), device=device)

    def transcribe_chunk(self, pcm, cancelled: Callable[[], bool]) -> list[Segment]:
        if cancelled():
            return []
        audio = np.asarray(pcm, dtype=np.float32).reshape(-1)
        return self._decode_audio(audio, cancelled, total_s=len(audio) / SAMPLE_RATE)

    def transcribe_file(
        self,
        pcm,
        cancelled: Callable[[], bool],
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Segment]:
        if cancelled():
            return []
        audio = np.asarray(pcm, dtype=np.float32).reshape(-1)
        total_s = max(len(audio) / SAMPLE_RATE, 0.001)
        return self._decode_audio(
            audio,
            cancelled,
            total_s=total_s,
            on_progress=on_progress,
        )

    def _decode_audio(
        self,
        audio: np.ndarray,
        cancelled: Callable[[], bool],
        *,
        total_s: float,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Segment]:
        if cancelled():
            return []
        result = self._model.transcribe(
            audio,
            language=None,
            fp16=self.device == "cuda",
        )
        if cancelled():
            return []
        segs: list[Segment] = []
        for item in result.get("segments") or []:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start)
            segs.append(
                Segment(
                    int(max(0.0, start) * 1000),
                    int(max(end, start) * 1000),
                    text,
                )
            )
            if on_progress is not None and total_s:
                on_progress(min(1.0, end / total_s))
        if on_progress is not None:
            on_progress(1.0)
        return segs


def load_backend(model_path: str | None = None):
    path = model_path or os.getenv("GIGAAM_ASR_PATH") or ""
    local = Path(path)
    if local.is_file() and local.suffix.lower() == ".pt":
        return OpenAIWhisperBackend(str(local))
    return FasterWhisperBackend(path)
