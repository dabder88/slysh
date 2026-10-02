"""Smoke: legacy settings secrets migrate to DPAPI (D.5)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from slysh.api import create_ui_app
    from slysh.compute import mutate_settings
    from slysh.db import Database
    from slysh.providers import openrouter_api_key

    home = Path(tempfile.mkdtemp(prefix="slysh-dpapi-"))
    os.environ["GIGAAM_DESKTOP_HOME"] = str(home)
    os.environ["GIGAAM_UI_AUTH"] = "0"
    os.environ["GIGAAM_LOOPBACK_STRICT"] = "0"
    mutate_settings(
        lambda data: data.update(
            {
                "providers": {
                    "openrouter": {"api_key": "sk-smoke-dpapi-key", "model": "openai/whisper-1"},
                }
            }
        )
    )
    db = Database(home / "app.db")
    create_ui_app(db=db, engine=None, auto_start_engine=False)
    if openrouter_api_key() != "sk-smoke-dpapi-key":
        print("smoke_secrets_dpapi_migration: FAIL key read", file=sys.stderr)
        return 1
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    if "api_key" in (settings.get("providers") or {}).get("openrouter", {}):
        print("smoke_secrets_dpapi_migration: FAIL key still in settings.json", file=sys.stderr)
        return 1
    if not (home / "secrets.dpapi").is_file():
        print("smoke_secrets_dpapi_migration: FAIL no secrets.dpapi", file=sys.stderr)
        return 1
    print("smoke_secrets_dpapi_migration: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
