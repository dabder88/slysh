"""Smoke: UI session gate with GIGAAM_UI_AUTH (D.2)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database

    home = Path(tempfile.mkdtemp(prefix="slysh-ui-auth-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    os.environ["GIGAAM_UI_AUTH"] = "1"
    os.environ["GIGAAM_UI_BOOTSTRAP_HTML"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"

    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app, raise_server_exceptions=False)
    bootstrap = app.state.ui_bootstrap_token

    if client.get("/api/library").status_code != 401:
        print("smoke_ui_auth_session: FAIL expected 401", file=sys.stderr)
        return 1

    sess = client.post("/api/ui/session", headers={"X-Slysh-Bootstrap": bootstrap})
    if sess.status_code != 200:
        print(f"smoke_ui_auth_session: FAIL session {sess.status_code}", file=sys.stderr)
        return 1

    if client.get("/api/library").status_code != 200:
        print("smoke_ui_auth_session: FAIL library after session", file=sys.stderr)
        return 1

    index = client.get("/")
    if "__SLYSH_BOOTSTRAP__" in index.text:
        print("smoke_ui_auth_session: FAIL bootstrap leaked in HTML", file=sys.stderr)
        return 1

    print("smoke_ui_auth_session: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
