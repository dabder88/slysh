"""Detect GPU runtime failures and fall back to CPU for local ASR."""
from __future__ import annotations

import logging
import os

_GPU_ERROR_MARKERS = (
    "cublas",
    "cudnn",
    "cuda error",
    "cuda runtime",
    "device-side assert",
    "out of memory",
    "c10::",
)


def is_gpu_runtime_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _GPU_ERROR_MARKERS)


def force_cpu_env() -> None:
    os.environ["GIGAAM_FORCE_CPU"] = "1"
    os.environ["GIGAAM_DEVICE"] = "cpu"


def log_gpu_fallback(exc: BaseException) -> None:
    logging.warning("GPU ASR failed (%s), switching to CPU for this engine process", exc)


def format_job_asr_error(exc: BaseException) -> str:
    text = str(exc).strip() or "Ошибка распознавания"
    if is_gpu_runtime_error(exc):
        return (
            f"{text}. Если ошибка повторяется, в Настройках → Система выберите "
            "устройство «Только CPU» или перезапустите Slysh."
        )
    return text
