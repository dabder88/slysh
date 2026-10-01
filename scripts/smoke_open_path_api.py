"""Smoke: POST /api/open-path returns 404 for missing files (B5 contract)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database

    home = Path(tempfile.mkdtemp(prefix="slysh-open-path-"))
    db = Database(home / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))

    missing = str(home / "no-such-file.txt")
    resp = client.post("/api/open-path", json={"path": missing, "reveal": False})
    if resp.status_code != 404:
        print(f"smoke_open_path_api: FAIL expected 404 got {resp.status_code}", file=sys.stderr)
        return 1

    real = home / "exists.txt"
    real.write_text("ok", encoding="utf-8")
    resp_ok = client.post(
        "/api/open-path",
        json={"path": str(real), "reveal": False},
    )
    if resp_ok.status_code != 200:
        print(f"smoke_open_path_api: FAIL existing file {resp_ok.status_code}", file=sys.stderr)
        return 1

    print("smoke_open_path_api: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
