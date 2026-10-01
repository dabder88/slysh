"""Smoke: FastAPI lifespan calls shutdown_ui_runtime on server stop."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("GIGAAM_SKIP_ENGINE", "1")
os.environ["GIGAAM_UI_AUTH"] = "0"
os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database

    home = Path(tempfile.mkdtemp(prefix="slysh-lifespan-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    db = Database(home / "app.db")
    app = create_ui_app(db, engine=None, auto_start_engine=False)
    with TestClient(app) as client:
        resp = client.get("/api/app/info")
        if resp.status_code != 200:
            print(f"smoke_ui_lifespan_shutdown: FAIL status {resp.status_code}", file=sys.stderr)
            return 1
    if getattr(app.state, "engine_proc", None) is not None:
        print("smoke_ui_lifespan_shutdown: FAIL engine_proc still set", file=sys.stderr)
        return 1
    print("smoke_ui_lifespan_shutdown: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
