"""Locale JSON parity and user-visible string quality."""

from __future__ import annotations

import json
import re
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[1] / "web" / "locales"
INDIRECTION = re.compile(r"^[a-z][\w]*\.[\w\u0400-\u04FF]+$")


def _load(name: str) -> dict:
    return json.loads((LOCALES / name).read_text(encoding="utf-8"))


def _string_values(obj, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(val, str):
                out.append((path, val))
            elif isinstance(val, dict):
                out.extend(_string_values(val, path))
    return out


def test_locale_files_share_same_key_paths() -> None:
    ru = _load("ru.json")
    en = _load("en.json")

    def paths(d: dict, prefix: str = "") -> set[str]:
        found: set[str] = set()
        for key, val in d.items():
            p = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                found |= paths(val, p)
            else:
                found.add(p)
        return found

    ru_paths = paths(ru)
    en_paths = paths(en)
    assert ru_paths == en_paths, f"key mismatch ru-only={ru_paths - en_paths} en-only={en_paths - ru_paths}"


def test_no_indirection_values_in_locales() -> None:
    for name in ("ru.json", "en.json"):
        data = _load(name)
        bad = [(path, val) for path, val in _string_values(data) if INDIRECTION.match(val)]
        assert not bad, f"{name} has key indirection values: {bad[:5]}"
