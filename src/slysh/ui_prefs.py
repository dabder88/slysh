from __future__ import annotations

from typing import Any

from slysh.compute import mutate_settings

MAX_EXPORT_FAVORITE_DIRS = 12


def _coerce_bool(value: object) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_skip_exit_confirm() -> bool:
    from slysh.compute import _read_settings

    ui = _read_settings().get("ui")
    if not isinstance(ui, dict):
        return False
    return _coerce_bool(ui.get("skip_exit_confirm"))


def save_skip_exit_confirm(skip: bool) -> None:
    flag = bool(skip)

    def patch(data: dict[str, Any]) -> None:
        ui = data.get("ui")
        if not isinstance(ui, dict):
            ui = {}
            data["ui"] = ui
        ui["skip_exit_confirm"] = flag

    mutate_settings(patch)


def normalize_export_dirs(paths: object) -> list[str]:
    if not isinstance(paths, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in paths:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= MAX_EXPORT_FAVORITE_DIRS:
            break
    return out


def load_export_favorite_dirs() -> list[str]:
    from slysh.compute import _read_settings

    ui = _read_settings().get("ui")
    if not isinstance(ui, dict):
        return []
    return normalize_export_dirs(ui.get("export_favorite_dirs"))


def save_export_favorite_dirs(paths: object) -> list[str]:
    normalized = normalize_export_dirs(paths)

    def patch(data: dict[str, Any]) -> None:
        ui = data.get("ui")
        if not isinstance(ui, dict):
            ui = {}
            data["ui"] = ui
        ui["export_favorite_dirs"] = normalized

    mutate_settings(patch)
    return normalized


def merge_export_favorite_dirs(paths: object) -> list[str]:
    merged = [*load_export_favorite_dirs(), *normalize_export_dirs(paths)]
    return save_export_favorite_dirs(merged)
