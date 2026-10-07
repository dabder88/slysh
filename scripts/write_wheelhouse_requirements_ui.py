"""Build hash-free requirements-ui.txt for offline uv pip sync from uv export + wheelhouse."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _normalize_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _marker_ok(marker: str) -> bool:
    """Keep lines applicable to Windows CPython wheelhouse (payload build host)."""
    m = marker.strip().lower()
    if not m:
        return True
    if "sys_platform" in m:
        if "win32" in m:
            return True
        if "darwin" in m or "openbsd" in m or "linux" in m:
            return False
    if "implementation_name" in m and "pypy" in m:
        return True
    return True


def _parse_export_lines(text: str) -> list[tuple[str, str]]:
    """Return (distribution_name, version) from uv export requirements.txt."""
    raw = text.replace("\\\n", " ")
    out: list[tuple[str, str]] = []
    spec_re = re.compile(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^;\s\\]+)",
        re.MULTILINE,
    )
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash"):
            continue
        m = spec_re.match(line)
        if not m:
            continue
        name, ver = m.group(1), m.group(2).strip()
        if ";" in line:
            marker = line.split(";", 1)[1]
            if not _marker_ok(marker):
                continue
        out.append((name, ver))
    return out


def _wheel_index(wheelhouse: Path) -> dict[str, list[Path]]:
    idx: dict[str, list[Path]] = {}
    for wh in wheelhouse.glob("*.whl"):
        stem = wh.name.split("-", 1)[0]
        key = _normalize_name(stem)
        idx.setdefault(key, []).append(wh)
    return idx


def build_requirements_ui(
    export_path: Path,
    wheelhouse: Path,
    app_version: str,
    out_path: Path,
) -> None:
    specs = _parse_export_lines(export_path.read_text(encoding="utf-8"))
    specs.append(("slysh", app_version))
    wheels = _wheel_index(wheelhouse)
    lines: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for name, ver in specs:
        key = _normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        if key not in wheels:
            missing.append(f"{name}=={ver}")
            continue
        lines.append(f"{name}=={ver}")
    if missing:
        raise SystemExit(
            "write_wheelhouse_requirements_ui: no wheel for: " + ", ".join(missing)
        )
    out_path.write_text("\n".join(sorted(lines, key=str.lower)) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: write_wheelhouse_requirements_ui.py "
            "<export.txt> <wheelhouse_dir> <app_version> <out requirements-ui.txt>",
            file=sys.stderr,
        )
        return 2
    build_requirements_ui(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        sys.argv[3],
        Path(sys.argv[4]),
    )
    print(f"write_wheelhouse_requirements_ui: {sys.argv[4]} ({Path(sys.argv[4]).read_text().count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
