"""Smoke: legacy.js must not export the same name twice (inline + export block)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEGACY = ROOT / "web" / "js" / "legacy.js"

INLINE_EXPORT = re.compile(
    r"^export\s+(?:async\s+)?function\s+(\w+)|^export\s+const\s+(\w+)",
    re.MULTILINE,
)
EXPORT_BLOCK = re.compile(r"^export\s*\{([^}]+)\}\s*;?\s*$", re.MULTILINE | re.DOTALL)


def _fail(msg: str) -> int:
    print(f"smoke_web_legacy_exports: FAIL: {msg}", file=sys.stderr)
    return 1


def check_legacy_exports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    inline: set[str] = set()
    for m in INLINE_EXPORT.finditer(text):
        name = m.group(1) or m.group(2)
        if name:
            inline.add(name)
    block_match = None
    for m in EXPORT_BLOCK.finditer(text):
        block_match = m
    if block_match is None:
        raise ValueError(f"no export {{ }} block in {path}")
    block_names: set[str] = set()
    for part in block_match.group(1).split(","):
        name = part.strip().split()[0] if part.strip() else ""
        if name:
            block_names.add(name)
    return sorted(inline & block_names)


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else [DEFAULT_LEGACY]
    for path in paths:
        if not path.is_file():
            return _fail(f"missing {path}")
        dupes = check_legacy_exports(path)
        if dupes:
            return _fail(f"{path}: duplicate exports {dupes}")
    print("smoke_web_legacy_exports: OK", [str(p) for p in paths])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
