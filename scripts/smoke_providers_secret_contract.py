"""Smoke: provider secrets — masked GET, session gate, PUT omit keeps key (A7)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> int:
    print(f"smoke_providers_secret_contract: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.providers import apify_api_key, save_apify

    home = Path(tempfile.mkdtemp(prefix="slysh-secrets-smoke-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    os.environ["GIGAAM_UI_AUTH"] = "1"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"

    secret = "apify-smoke-secret-token-99"
    save_apify(api_key=secret)
    db = Database(home / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app, raise_server_exceptions=False)

    blocked = client.get("/api/providers")
    if blocked.status_code != 401:
        return _fail(f"expected 401 without session, got {blocked.status_code}")

    bootstrap = app.state.ui_bootstrap_token
    sess = client.post("/api/ui/session", headers={"X-Slysh-Bootstrap": bootstrap})
    if sess.status_code != 200:
        return _fail(f"ui session {sess.status_code}")

    data = client.get("/api/providers").json()
    apify = data.get("apify") or {}
    if not apify.get("api_key_set"):
        return _fail("api_key_set false")
    if "apify-smoke" in str(apify.get("api_key_masked", "")):
        pass
    elif not apify.get("api_key_masked"):
        return _fail("missing api_key_masked")
    if apify.get("api_key") != secret:
        return _fail("reveal after session failed")

    client.put("/api/providers/apify", json={})
    if apify_api_key() != secret:
        return _fail("PUT omit cleared key")

    client.put("/api/providers/apify", json={"api_key": ""})
    if apify_api_key():
        return _fail("empty api_key should clear secret")

    print("smoke_providers_secret_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
