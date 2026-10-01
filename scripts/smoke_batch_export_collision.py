"""Smoke: batch fixed export keeps both same-stem files (wave A5)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_batch_export_collision: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from slysh.batch_runner import _export_batch_job
    from slysh.db import Database
    from slysh.models import JobKind, Segment

    home = Path(tempfile.mkdtemp(prefix="slysh-batch-export-"))
    db = Database(home / "app.db")
    out = home / "out"
    out.mkdir()
    used: set[str] = set()
    for folder, text in (("one", "alpha"), ("two", "beta")):
        src = home / folder / "clip.wav"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"1")
        jid = db.create_job(JobKind.FILE, str(src))
        db.replace_segments(jid, [Segment(0, 50, text)])
        rules = {
            "export": True,
            "export_fmt": "txt",
            "export_dir_mode": "fixed",
            "export_dir": str(out),
        }
        _export_batch_job(db, jid, db.get_job(jid) or {}, rules, used_names=used)

    files = list(out.glob("*.txt"))
    if len(files) != 2:
        return _fail(f"expected 2 exports, got {[f.name for f in files]}")
    print("smoke_batch_export_collision: OK", [f.name for f in files])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
