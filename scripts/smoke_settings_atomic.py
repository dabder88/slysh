"""Smoke: atomic settings mutate + backup recovery."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slysh.settings_store import load_json_resilient, mutate_json, save_json


def main() -> int:
    raw = os.environ.get("SLYSH_SMOKE_SETTINGS", "").strip()
    path = Path(raw) if raw else ROOT / "dist" / "smoke-settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.unlink()
    bak = path.with_suffix(path.suffix + ".bak")
    if bak.is_file():
        bak.unlink()

    save_json(path, {"a": 1})

    def add_b(data: dict) -> None:
        data["b"] = data.get("b", 0) + 1

    errors: list[str] = []

    def worker() -> None:
        try:
            for _ in range(20):
                mutate_json(path, add_b)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    if errors:
        print("smoke_settings_atomic: FAIL:", errors[0], file=sys.stderr)
        return 1

    data = load_json_resilient(path)
    if data.get("a") != 1 or int(data.get("b", 0)) != 80:
        print(f"smoke_settings_atomic: FAIL unexpected {data}", file=sys.stderr)
        return 1

    save_json(path, {"step": 1})
    save_json(path, {"step": 2})
    path.write_text("{not-json", encoding="utf-8")
    restored = load_json_resilient(path)
    if restored.get("step") != 1:
        print(f"smoke_settings_atomic: FAIL backup restore {restored}", file=sys.stderr)
        return 1

    print("smoke_settings_atomic: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
