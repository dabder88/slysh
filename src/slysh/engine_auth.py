"""Shared engine HTTP token (wave D)."""
from __future__ import annotations

import os

ENGINE_TOKEN_ENV = "GIGAAM_ENGINE_TOKEN"
ENGINE_TOKEN_HEADER = "X-Gigaam-Engine-Token"


def engine_token_from_env() -> str:
    return (os.environ.get(ENGINE_TOKEN_ENV) or "").strip()


def engine_auth_required() -> bool:
    return bool(engine_token_from_env())


def engine_auth_headers() -> dict[str, str]:
    token = engine_token_from_env()
    if not token:
        return {}
    return {ENGINE_TOKEN_HEADER: token}
