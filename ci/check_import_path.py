"""Wave 0 / F: assert slysh imports from this repo's src/."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("GIGAAM_DESKTOP_HOME", tempfile.mkdtemp(prefix="slysh-ci-"))

import slysh  # noqa: E402

expected = (SRC / "slysh").resolve()
actual = Path(slysh.__file__).resolve().parent
if actual != expected:
    print(f"check_import_path: FAIL expected {expected}, got {actual}", file=sys.stderr)
    raise SystemExit(1)
print(f"check_import_path: OK ({actual})")
