from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from slysh.models import Segment

DIARIZATION_MISSING = (
    "Нет библиотек диаризации (NeMo). Закройте приложение и запустите "
    "Slysh.bat — он поставит пакеты спикеров. "
    "Либо вручную: uv sync --extra engine --extra diarization --extra youtube"
)

TARGET_SAMPLE_RATE = 16000


def _map_by_overlap(
    segments: list[Segment],
    turns: list[tuple[int, int, str]],
) -> list[Segment]:
    labeled: list[Segment] = []
    for seg in segments:
        best_speaker = None
        best_overlap = 0
        for start_ms, end_ms, speaker in turns:
            overlap = min(seg.end_ms, end_ms) - max(seg.start_ms, start_ms)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        labeled.append(
            Segment(
                seg.start_ms,
                seg.end_ms,
                seg.text,
                speaker=best_speaker or "SPEAKER_00",
            )
        )
    return labeled


def _diarizer_name() -> str:
    name = (os.environ.get("GIGAAM_DIARIZER") or "sortformer").strip().lower()
    if name in {"msdd", "sortformer"}:
        return name
    return "sortformer"


def _load_msdd_class():
    from slysh.diarization import MSDDDiarizer, SortformerDiarizer

    name = _diarizer_name()
    if name == "msdd":
        return MSDDDiarizer
    return SortformerDiarizer


def _import_msdd_deps():
    try:
        import torch

        msdd_cls = _load_msdd_class()
    except (ImportError, OSError) as exc:
        raise RuntimeError(DIARIZATION_MISSING) from exc
    return torch, msdd_cls


def _load_audio(source_path: str):
    import numpy as np

    try:
        import soundfile as sf

        data, sr = sf.read(source_path, always_2d=False)
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != TARGET_SAMPLE_RATE and data.size:
            n = max(1, int(round(data.size * TARGET_SAMPLE_RATE / float(sr))))
            data = np.interp(
                np.linspace(0, data.size - 1, n),
                np.arange(data.size),
                data,
            ).astype(np.float32)
        return data.reshape(-1)
    except Exception:
        from slysh.decode import decode_pcm_16k_mono

        pcm, _sr = decode_pcm_16k_mono(source_path)
        return np.asarray(pcm, dtype=np.float32).reshape(-1)


@contextmanager
def _hide_cuda_from_torch(torch_mod, device: str):
    if device != "cpu" or not torch_mod.cuda.is_available():
        yield
        return
    original = torch_mod.cuda.is_available
    torch_mod.cuda.is_available = lambda: False
    try:
        yield
    finally:
        torch_mod.cuda.is_available = original


def _speaker_key(speaker: object) -> str:
    if isinstance(speaker, int):
        return f"SPEAKER_{speaker:02d}"
    name = str(speaker)
    if name.isdigit():
        return f"SPEAKER_{int(name):02d}"
    if name.upper().startswith("SPEAKER_"):
        return name
    return f"SPEAKER_{name}"


def _turns_from_result(result) -> list[tuple[int, int, str]]:
    turns: list[tuple[int, int, str]] = []
    for item in result or []:
        if not isinstance(item, (tuple, list)) or len(item) < 3:
            continue
        start_ms, end_ms, speaker = item[0], item[1], item[2]
        turns.append((int(start_ms), int(end_ms), _speaker_key(speaker)))
    return turns


def _run_diarizer(torch_mod, msdd_cls, source_path: str, audio):
    from slysh.rnnt_backend import resolve_device

    device = resolve_device()
    seconds = len(audio) / float(TARGET_SAMPLE_RATE) if len(audio) else 0
    logging.info(
        "speakers: %s on %s, audio %.1f min",
        _diarizer_name(),
        device,
        seconds / 60.0,
    )
    try:
        try:
            diarizer = msdd_cls(device=device)
        except TypeError:
            diarizer = msdd_cls(device)
        waveform = torch_mod.from_numpy(audio)
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        with _hide_cuda_from_torch(torch_mod, device):
            try:
                return diarizer.diarize(waveform)
            except TypeError:
                return diarizer.diarize(source_path)
    except Exception as exc:
        raise RuntimeError(f"диаризация не удалась: {exc}") from exc


class MsddSpeakersBackend:
    def label(self, source_path: str, segments: list[Segment]) -> list[Segment]:
        torch_mod, msdd_cls = _import_msdd_deps()
        try:
            audio = _load_audio(source_path)
            result = _run_diarizer(torch_mod, msdd_cls, source_path, audio)
            return _map_by_overlap(segments, _turns_from_result(result))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"диаризация не удалась: {exc}") from exc
