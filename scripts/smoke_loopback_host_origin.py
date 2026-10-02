"""Smoke: GIGAAM_LOOPBACK_STRICT rejects bad Host/Origin on mutating /api (D.3)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "1"
    # TestClient uses client host "testclient"; same allowance as pytest (in-process smoke).
    os.environ.setdefault("PYTEST_CURRENT_TEST", "smoke_loopback_host_origin")
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database

    home = Path(tempfile.mkdtemp(prefix="slysh-loopback-"))
    db = Database(home / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))

    bad = client.put(
        "/api/compute",
        json={"preference": "cpu"},
        headers={"Host": "evil.example", "Origin": "http://evil.example"},
    )
    if bad.status_code != 403:
        print(f"smoke_loopback_host_origin: FAIL bad host {bad.status_code}", file=sys.stderr)
        return 1

    no_origin = client.put("/api/compute", json={"preference": "cpu"})
    if no_origin.status_code != 403:
        print(f"smoke_loopback_host_origin: FAIL no origin {no_origin.status_code}", file=sys.stderr)
        return 1

    ok = client.put(
        "/api/compute",
        json={"preference": "cpu"},
        headers={"Origin": "http://testserver", "Referer": "http://testserver/"},
    )
    if ok.status_code != 200:
        print(f"smoke_loopback_host_origin: FAIL valid origin {ok.status_code}", file=sys.stderr)
        return 1

    print("smoke_loopback_host_origin: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
