from __future__ import annotations

import argparse
import sys

from slysh.catalog import FASTER_WHISPER_DOWNLOAD_SIZES, whisper_size_from_model_id
from slysh.paths import logs_dir, project_models_dir

MODEL_DOWNLOAD_LOG = "model-download.log"


def model_download_log_path():
    return logs_dir() / MODEL_DOWNLOAD_LOG


def whisper_repo_id(size: str) -> str:
    return f"Systran/faster-whisper-{size}"


def download_whisper_size(size: str) -> None:
    if size not in FASTER_WHISPER_DOWNLOAD_SIZES:
        raise ValueError(f"Неподдерживаемый размер Whisper: {size}")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Нет пакета huggingface_hub. Установите локальные пакеты расшифровки (engine extras)."
        ) from exc
    dest = project_models_dir() / f"faster-whisper-{size}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Systran/faster-whisper-{size} into {dest}…", flush=True)
    snapshot_download(
        repo_id=whisper_repo_id(size),
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    print("done", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download Faster-Whisper weights into models/")
    parser.add_argument("--size", help="Whisper size (tiny, small, …)")
    parser.add_argument("--id", help="Catalog id, e.g. whisper:small")
    args = parser.parse_args(argv)
    size = (args.size or "").strip()
    if not size and args.id:
        size = whisper_size_from_model_id(args.id) or ""
    if not size:
        parser.error("specify --size or --id whisper:<size>")
    download_whisper_size(size)


if __name__ == "__main__":
    main()
