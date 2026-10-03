from __future__ import annotations

from typing import Any

from slysh.compute import mutate_settings


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
