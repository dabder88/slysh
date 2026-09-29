"""Loopback UI session token (opt-in via GIGAAM_UI_AUTH=1)."""
from __future__ import annotations

import os
import secrets
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response

_UI_AUTH_ENV = "GIGAAM_UI_AUTH"
_PUBLIC_PATHS = frozenset({"/", "/health", "/api/health", "/api/app/info"})


def ui_auth_enabled() -> bool:
    return os.environ.get(_UI_AUTH_ENV) == "1"


def install_ui_auth(app: FastAPI) -> str:
    token = secrets.token_urlsafe(32)
    app.state.ui_auth_token = token

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable):
        if not ui_auth_enabled():
            return await call_next(request)
        path = request.url.path
        if path.startswith("/web/") or path in _PUBLIC_PATHS:
            return await call_next(request)
        if path.endswith((".css", ".js", ".ico", ".png", ".svg", ".woff2")):
            return await call_next(request)
        cookie = request.cookies.get("slysh_ui_session")
        header = request.headers.get("x-slysh-ui-token")
        expected = getattr(app.state, "ui_auth_token", None)
        if cookie == expected or header == expected:
            return await call_next(request)
        raise HTTPException(status_code=401, detail="Требуется авторизация UI.")

    return token


def set_ui_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "slysh_ui_session",
        token,
        httponly=True,
        samesite="strict",
        secure=False,
    )
