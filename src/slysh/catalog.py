from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from slysh.paths import catalog_roots, gigaam_download_root, has_gigaam_weights, project_models_dir
from slysh.providers import (
    CLI_GEMINI_ID,
    OPENROUTER_DEFAULT_MODEL,
    custom_is_ready,
    find_gemini_binary,
    list_custom_providers,
    list_http_presets,
    openrouter_api_key,
    openrouter_cached_models,
    openrouter_model,
)

GIGAAM_ID = "gigaam"
_WEIGHT_NAMES = ("model.bin", "pytorch_model.bin")
FASTER_WHISPER_DOWNLOAD_SIZES: tuple[str, ...] = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
)
DOWNLOADABLE_LOCAL_IDS: frozenset[str] = frozenset(
    {GIGAAM_ID, *(f"whisper:{size}" for size in FASTER_WHISPER_DOWNLOAD_SIZES)}
)

# Оценки объёма скачивания для UI (Systran faster-whisper-* / GigaAM e2e_rnnt).
GIGAAM_DOWNLOAD_BYTES_ESTIMATE = 480 * 1024 * 1024
WHISPER_DOWNLOAD_BYTES_ESTIMATE: dict[str, int] = {
    "tiny": 75 * 1024 * 1024,
    "base": 145 * 1024 * 1024,
    "small": 480 * 1024 * 1024,
    "medium": 1500 * 1024 * 1024,
    "large-v2": 3100 * 1024 * 1024,
    "large-v3": 3100 * 1024 * 1024,
}


@dataclass(frozen=True)
class ModelItem:
    id: str
    label: str
    backend: str
    path: str
    ready: bool
    kind: str = "local"
    hint: str = ""
    downloadable: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "backend": self.backend,
            "path": self.path,
            "ready": self.ready,
            "kind": self.kind,
            "hint": self.hint,
            "downloadable": self.downloadable,
        }


def _snapshot_complete(folder: Path) -> bool:
    if not (folder / "config.json").is_file():
        return False
    return any((folder / name).is_file() for name in _WEIGHT_NAMES)


def _best_snapshot(model_dir: Path) -> Path | None:
    snapshots = model_dir / "snapshots"
    candidates: list[Path] = []
    if snapshots.is_dir():
        candidates.extend(p for p in snapshots.iterdir() if p.is_dir())
    candidates.append(model_dir)
    complete = [p for p in candidates if _snapshot_complete(p)]
    if not complete:
        return None
    return max(complete, key=lambda p: p.stat().st_mtime)


def _whisper_size_from_hub_name(name: str) -> str | None:
    marker = "--faster-whisper-"
    if marker not in name:
        return None
    return name.split(marker, 1)[1] or None


def _whisper_size_from_flat_name(name: str) -> str | None:
    prefix = "faster-whisper-"
    if name.startswith(prefix) and len(name) > len(prefix):
        return name[len(prefix) :]
    return None


def _whisper_label(size: str) -> str:
    return f"Whisper {size}"


def _gigaam_item(root: Path) -> ModelItem | None:
    folder = root / "gigaam"
    if not has_gigaam_weights(root):
        return None
    return ModelItem(
        id=GIGAAM_ID,
        label="GigaAM (e2e RNNT)",
        backend="gigaam",
        path=str(folder),
        ready=True,
    )


def _whisper_item(size: str, snapshot: Path) -> ModelItem:
    return ModelItem(
        id=f"whisper:{size}",
        label=_whisper_label(size),
        backend="whisper",
        path=str(snapshot),
        ready=True,
    )


def _pt_size(path: Path) -> str | None:
    if path.suffix.lower() != ".pt":
        return None
    stem = path.stem.strip()
    return stem or None


def scan_root(root: Path) -> list[ModelItem]:
    items: list[ModelItem] = []
    if not root.is_dir():
        return items
    gigaam = _gigaam_item(root)
    if gigaam:
        items.append(gigaam)
    seen: set[str] = set()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        size = _whisper_size_from_hub_name(child.name) or _whisper_size_from_flat_name(
            child.name
        )
        if not size:
            continue
        snapshot = _best_snapshot(child)
        if snapshot is None:
            continue
        items.append(_whisper_item(size, snapshot))
        seen.add(f"whisper:{size}")
    pt_dirs = [root / "whisper", root]
    for folder in pt_dirs:
        if not folder.is_dir():
            continue
        for pt in folder.glob("*.pt"):
            size = _pt_size(pt)
            if not size:
                continue
            model_id = f"whisper:{size}"
            if model_id in seen:
                continue
            items.append(_whisper_item(size, pt))
            seen.add(model_id)
    return items


def whisper_size_from_model_id(model_id: str) -> str | None:
    wanted = str(model_id or "").strip()
    prefix = "whisper:"
    if not wanted.startswith(prefix):
        return None
    size = wanted[len(prefix) :].strip()
    return size or None


def is_downloadable_local_id(model_id: str) -> bool:
    return str(model_id or "").strip() in DOWNLOADABLE_LOCAL_IDS


def model_download_bytes_estimate(model_id: str) -> int | None:
    wanted = str(model_id or "").strip()
    if wanted == GIGAAM_ID:
        return GIGAAM_DOWNLOAD_BYTES_ESTIMATE
    size = whisper_size_from_model_id(wanted)
    if size and size in WHISPER_DOWNLOAD_BYTES_ESTIMATE:
        return WHISPER_DOWNLOAD_BYTES_ESTIMATE[size]
    return None


def model_download_watch_paths(model_id: str) -> list[Path]:
    wanted = str(model_id or "").strip()
    root = project_models_dir()
    if wanted == GIGAAM_ID:
        return [gigaam_download_root(), root / "huggingface"]
    size = whisper_size_from_model_id(wanted)
    if size:
        return [root / f"faster-whisper-{size}"]
    return []


def list_local_catalog(roots: list[Path] | None = None) -> list[ModelItem]:
    scan_roots = roots if roots is not None else catalog_roots()
    root = scan_roots[0] if scan_roots else project_models_dir()
    installed = {item.id: item for item in list_models(roots)}
    catalog_ids = {GIGAAM_ID, *(f"whisper:{size}" for size in FASTER_WHISPER_DOWNLOAD_SIZES)}
    ordered: list[ModelItem] = []
    if GIGAAM_ID in installed:
        ordered.append(installed[GIGAAM_ID])
    else:
        ordered.append(
            ModelItem(
                id=GIGAAM_ID,
                label="GigaAM (e2e RNNT)",
                backend="gigaam",
                path=str(root / "gigaam"),
                ready=False,
                downloadable=True,
            )
        )
    for size in FASTER_WHISPER_DOWNLOAD_SIZES:
        model_id = f"whisper:{size}"
        if model_id in installed:
            ordered.append(installed[model_id])
        else:
            ordered.append(
                ModelItem(
                    id=model_id,
                    label=_whisper_label(size),
                    backend="whisper",
                    path=str(root / f"faster-whisper-{size}"),
                    ready=False,
                    downloadable=True,
                )
            )
    extras = [
        item for item in installed.values() if item.id not in catalog_ids
    ]
    ordered.extend(sorted(extras, key=lambda item: item.label.lower()))
    return ordered


def list_models(roots: list[Path] | None = None) -> list[ModelItem]:
    found: dict[str, ModelItem] = {}
    for root in roots if roots is not None else catalog_roots():
        for item in scan_root(root):
            if item.id not in found:
                found[item.id] = item
    ordered: list[ModelItem] = []
    if GIGAAM_ID in found:
        ordered.append(found.pop(GIGAAM_ID))
    ordered.extend(sorted(found.values(), key=lambda item: item.label.lower()))
    return ordered


def list_remote_models(
    which: Callable[[str], str | None] | None = None,
) -> list[ModelItem]:
    items: list[ModelItem] = []
    key_ok = bool(openrouter_api_key())
    slugs = openrouter_cached_models()
    default = openrouter_model() or OPENROUTER_DEFAULT_MODEL
    seen: set[str] = set()
    if not slugs:
        slugs = [{"id": default, "label": f"OpenRouter {default}"}]
    elif not any(row["id"] == default for row in slugs):
        slugs = [{"id": default, "label": f"OpenRouter {default}"}] + slugs
    for row in slugs:
        slug = row["id"]
        model_id = f"openrouter:{slug}"
        if model_id in seen:
            continue
        seen.add(model_id)
        hint = "" if key_ok else "Сохраните API-ключ OpenRouter в настройках."
        items.append(
            ModelItem(
                id=model_id,
                label=f"OpenRouter · {row['label']}",
                backend="openrouter",
                path="",
                ready=key_ok,
                kind="http",
                hint=hint,
            )
        )
    for row in list_http_presets():
        ready = bool(row["ready"])
        hint = "" if ready else f"Сохраните API-ключ {row['name']} в настройках."
        items.append(
            ModelItem(
                id=f"http:{row['id']}",
                label=f"{row['name']} · {row['model']}",
                backend="http",
                path=row["endpoint"],
                ready=ready,
                kind="http",
                hint=hint,
            )
        )
    for row in list_custom_providers():
        ready = custom_is_ready(row)
        hint = "" if ready else "Укажите endpoint, модель и ключ."
        items.append(
            ModelItem(
                id=f"custom:{row['id']}",
                label=f"{row['name']} · {row['model']}",
                backend="custom",
                path=row["endpoint"],
                ready=ready,
                kind="http",
                hint=hint,
            )
        )
    gemini = find_gemini_binary(which=which)
    items.append(
        ModelItem(
            id=CLI_GEMINI_ID,
            label="Gemini CLI",
            backend="cli",
            path=gemini or "",
            ready=bool(gemini),
            kind="cli",
            hint=""
            if gemini
            else "Установите Gemini CLI и войдите в аккаунт Google.",
        )
    )
    return items


def list_asr_models(
    roots: list[Path] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> list[ModelItem]:
    return [*list_local_catalog(roots), *list_remote_models(which=which)]


def get_model(model_id: str, roots: list[Path] | None = None) -> ModelItem | None:
    wanted = str(model_id or "").strip()
    for item in list_asr_models(roots):
        if item.id == wanted:
            return item
    return None
