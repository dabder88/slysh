from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import MutableMapping
from pathlib import Path

from slysh.paths import app_dir

PREFERENCES = ("auto", "gpu", "cpu")
ENGINE_MODES = ("auto", "cloud_only", "local")

EXPLANATIONS = {
    "gpu": (
        "Видеокарта NVIDIA. Быстрее на длинных файлах и при разметке спикеров. "
        "Нужна CUDA-сборка torch; иначе будет тот же CPU, только медленнее."
    ),
    "cpu": (
        "Только процессор. Работает без видеокарты, но длинный файл "
        "и спикеры могут идти десятки минут или часы и съедать много RAM."
    ),
    "auto": (
        "GPU, если CUDA доступна прямо сейчас, иначе процессор. "
        "Удобно, пока не уверены, поставилась ли GPU-сборка torch."
    ),
}

EXPLANATIONS_EN = {
    "gpu": (
        "NVIDIA GPU. Fast speaker diarization when CUDA torch is installed; "
        "otherwise falls back to CPU and runs slower."
    ),
    "cpu": (
        "CPU only. Works without a GPU, but long files and speaker ID "
        "can take a long time and use a lot of RAM."
    ),
    "auto": (
        "GPU when CUDA is available now, otherwise CPU. "
        "Handy while you are unsure whether the CUDA build of torch is installed."
    ),
}

WARNINGS = {
    "gpu_no_cuda": (
        "Выбран GPU, но CUDA недоступна (часто из‑за CPU-сборки torch). "
        "Расшифровка пойдёт на процессоре, пока не поставите CUDA torch."
    ),
}

WARNINGS_EN = {
    "gpu_no_cuda": (
        "GPU is selected but CUDA is unavailable (often a CPU-only torch build). "
        "Transcription will use CPU until you install CUDA torch."
    ),
}


def settings_path() -> Path:
    return app_dir() / "settings.json"


def _read_settings() -> dict:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(data: dict) -> None:
    from slysh.settings_store import save_json

    save_json(settings_path(), data)


def load_preference() -> str:
    env = (os.getenv("GIGAAM_DEVICE") or "").strip().lower()
    if env in PREFERENCES:
        return env
    if (os.getenv("GIGAAM_FORCE_CPU") or "").lower() in {"1", "true", "yes"}:
        return "cpu"
    pref = str(_read_settings().get("compute") or "").strip().lower()
    if pref in PREFERENCES:
        return pref
    return "auto"


def load_engine_mode() -> str:
    mode = str(_read_settings().get("engine_mode") or "").strip().lower()
    if mode in ENGINE_MODES:
        return mode
    return "auto"


def save_engine_mode(mode: str) -> str:
    value = str(mode).strip().lower()
    if value not in ENGINE_MODES:
        raise ValueError("Нужно auto, cloud_only или local")
    data = _read_settings()
    data["engine_mode"] = value
    _write_settings(data)
    return value


def is_cloud_only() -> bool:
    return load_engine_mode() == "cloud_only"


def save_preference(preference: str) -> str:
    pref = str(preference).strip().lower()
    if pref not in PREFERENCES:
        raise ValueError("Нужно auto, gpu или cpu")
    data = _read_settings()
    data["compute"] = pref
    _write_settings(data)
    return pref


def load_asr_id() -> str:
    env = (os.getenv("GIGAAM_ASR_ID") or "").strip()
    if env:
        return env
    value = str(_read_settings().get("asr") or "").strip()
    return value or "gigaam"


def _is_remote_asr(model_id: str) -> bool:
    return str(model_id or "").startswith(("openrouter:", "custom:", "cli:", "http:"))


def load_asr_local_id() -> str:
    value = str(_read_settings().get("asr_local") or "").strip()
    current = load_asr_id()
    if value:
        return value
    return current if current and not _is_remote_asr(current) else "gigaam"


def load_asr_remote_id() -> str:
    value = str(_read_settings().get("asr_remote") or "").strip()
    current = load_asr_id()
    if value:
        return value
    return current if current and _is_remote_asr(current) else ""


def save_asr_id(model_id: str) -> str:
    value = str(model_id).strip()
    if not value:
        raise ValueError("Нужно выбрать модель")
    data = _read_settings()
    data["asr"] = value
    if _is_remote_asr(value):
        data["asr_remote"] = value
    else:
        data["asr_local"] = value
    _write_settings(data)
    return value


def write_asr_env(env: MutableMapping[str, str], model_id: str, path: str | None) -> None:
    env["GIGAAM_ASR_ID"] = model_id
    if model_id.startswith("whisper:"):
        env["GIGAAM_ASR_BACKEND"] = "whisper"
    elif model_id.startswith(("openrouter:", "custom:", "cli:", "http:")):
        env["GIGAAM_ASR_BACKEND"] = "remote"
    else:
        env["GIGAAM_ASR_BACKEND"] = "gigaam"
    if path:
        env["GIGAAM_ASR_PATH"] = path
    else:
        env.pop("GIGAAM_ASR_PATH", None)


def write_env(env: MutableMapping[str, str], preference: str) -> None:
    pref = str(preference).strip().lower()
    if pref not in PREFERENCES:
        pref = "auto"
    env["GIGAAM_DEVICE"] = pref
    if pref == "cpu":
        env["GIGAAM_FORCE_CPU"] = "1"
    else:
        env.pop("GIGAAM_FORCE_CPU", None)


def apply_preference(preference: str) -> str:
    pref = str(preference).strip().lower()
    if pref not in PREFERENCES:
        raise ValueError("Нужно auto, gpu или cpu")
    write_env(os.environ, pref)
    return pref


_cuda_cache: bool | None = None
_cuda_lock = threading.Lock()


def _probe_cuda_subprocess() -> bool:
    """CUDA probe in a child process so the UI never imports torch."""
    if os.environ.get("GIGAAM_FORCE_CPU") == "1":
        return False
    script = (
        "try:\n"
        " import torch\n"
        " print(1 if torch.cuda.is_available() else 0)\n"
        "except Exception:\n"
        " print(0)\n"
    )
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": 45,
        "check": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run([sys.executable, "-c", script], **kwargs)
        return completed.stdout.strip() == "1"
    except (OSError, subprocess.TimeoutExpired):
        return False


def warm_cuda_cache() -> None:
    global _cuda_cache
    with _cuda_lock:
        if _cuda_cache is not None:
            return
        _cuda_cache = _probe_cuda_subprocess()


def cuda_available() -> bool:
    global _cuda_cache
    with _cuda_lock:
        if _cuda_cache is not None:
            return _cuda_cache
    warm_cuda_cache()
    with _cuda_lock:
        return bool(_cuda_cache)


def compute_payload(ui_locale: str | None = None) -> dict:
    from slysh.ui_locale import load_ui_locale

    locale = (ui_locale or load_ui_locale() or "ru").lower()
    explanations = EXPLANATIONS_EN if locale == "en" else EXPLANATIONS
    warnings = WARNINGS_EN if locale == "en" else WARNINGS
    preference = load_preference()
    cuda = cuda_available()
    if preference == "cpu":
        effective = "cpu"
    elif cuda:
        effective = "gpu"
    else:
        effective = "cpu"
    warning = ""
    if preference == "gpu" and not cuda:
        warning = warnings["gpu_no_cuda"]
    return {
        "preference": preference,
        "cuda_available": cuda,
        "effective": effective,
        "warning": warning,
        "explanations": dict(explanations),
        "ui_locale": locale,
    }
