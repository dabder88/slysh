"""Wave E.4: updates require sha256 in release notes before download/apply."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_updates_sha256: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from slysh.updates import _parse_expected_sha256, _require_expected_sha256

    body = "Release notes\nsha256: a" * 0 + "sha256: " + ("ab" * 32) + "\n"
    parsed = _parse_expected_sha256(body)
    if not parsed or len(parsed) != 64:
        return _fail(f"parse body got {parsed!r}")

    good = {"expected_sha256": "a" * 64}
    try:
        _require_expected_sha256(good)
    except ValueError as exc:
        return _fail(f"require good: {exc}")

    try:
        _require_expected_sha256({"expected_sha256": "short"})
    except ValueError:
        pass
    else:
        return _fail("require must reject short digest")

    print("smoke_updates_sha256: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
