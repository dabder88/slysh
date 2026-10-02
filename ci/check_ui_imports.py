"""Wave F: UI modules must not import torch/gigaam/rnnt_backend (mirrors tests/test_ui_imports.py)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "slysh"

MODULES = (
    "app.py",
    "api.py",
    "db.py",
    "queue.py",
    "runtime_setup.py",
    "runtime_env.py",
    "providers.py",
    "remote_asr.py",
    "gemini_cli.py",
    "meeting_capture.py",
    "wasapi_loopback.py",
    "batch_runner.py",
    "speakers_engine.py",
)

NO_SPEAKERS_MSDD = frozenset({"api.py", "batch_runner.py", "speakers_engine.py"})


def main() -> int:
    for name in MODULES:
        tree = ast.parse((PKG / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in {"torch", "gigaam"}:
                        print(f"check_ui_imports: forbidden import {alias.name} in {name}", file=sys.stderr)
                        return 1
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if mod.startswith("torch") or mod == "gigaam" or mod == "slysh.rnnt_backend":
                    print(f"check_ui_imports: forbidden from {mod} in {name}", file=sys.stderr)
                    return 1
                if name in NO_SPEAKERS_MSDD and mod == "slysh.speakers_msdd":
                    print(f"check_ui_imports: lazy diarization only: {mod} in {name}", file=sys.stderr)
                    return 1
    print(f"check_ui_imports: OK ({len(MODULES)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
