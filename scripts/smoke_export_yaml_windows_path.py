"""Smoke: YAML front matter escapes Windows paths (A9)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_export_yaml_windows_path: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from slysh.export import write_media_markdown

    source = r'C:\Users\O\'Brien\clip "1".wav'
    out = Path(tempfile.mkdtemp()) / "out.md"
    write_media_markdown(
        out,
        title='Title "x"',
        source=source,
        kind="file",
        segments=[],
    )
    text = out.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return _fail("missing front matter")
    expected_source = f"source: {json.dumps(source, ensure_ascii=False)}"
    if expected_source not in text:
        return _fail(f"expected escaped source line, got:\n{text[:400]}")
    print("smoke_export_yaml_windows_path: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
