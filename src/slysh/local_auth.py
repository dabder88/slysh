"""Loopback UI session (wave D; enable with GIGAAM_UI_AUTH=1)."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

_UI_AUTH_ENV = "GIGAAM_UI_AUTH"
_BOOTSTRAP_HTML_ENV = "GIGAAM_UI_BOOTSTRAP_HTML"
_DEFAULT_COOKIE = "slysh_ui_session"
_PUBLIC_PATHS = frozenset(
    {
        "/",
        "/health",
        "/api/health",
        "/api/app/info",
        "/api/ui/session",
    }
)


def ui_auth_enabled() -> bool:
    return os.environ.get(_UI_AUTH_ENV) == "1"


def bootstrap_in_html_enabled() -> bool:
    return os.environ.get(_BOOTSTRAP_HTML_ENV, "0") == "1"


def ui_cookie_name(app: FastAPI) -> str:
    return str(getattr(app.state, "ui_cookie_name", None) or _DEFAULT_COOKIE)


def ui_session_valid(request: Request, app: FastAPI) -> bool:
    if not ui_auth_enabled():
        return True
    expected = getattr(app.state, "ui_auth_token", None)
    if not expected:
        return False
    cookie = request.cookies.get(ui_cookie_name(app))
    header = (request.headers.get("x-slysh-ui-token") or "").strip()
    return cookie == expected or header == expected


def install_ui_auth(app: FastAPI) -> str:
    bootstrap = secrets.token_urlsafe(32)
    session = secrets.token_urlsafe(32)
    app.state.ui_bootstrap_token = bootstrap
    app.state.ui_auth_token = session
    app.state.ui_cookie_name = f"slysh_{secrets.token_hex(8)}"

    @app.middleware("http")
    async def guard(request: Request, call_next: Callable):
        if not ui_auth_enabled():
            return await call_next(request)
        path = request.url.path
        if path.startswith("/web/") or path.startswith("/locales/"):
            return await call_next(request)
        if path == "/api/locale" and request.method == "GET":
            return await call_next(request)
        if path in _PUBLIC_PATHS:
            return await call_next(request)
        if path.endswith((".css", ".js", ".ico", ".png", ".svg", ".woff2", ".json")):
            return await call_next(request)
        cookie = request.cookies.get(ui_cookie_name(app))
        header = request.headers.get("x-slysh-ui-token")
        expected = getattr(app.state, "ui_auth_token", None)
        if cookie == expected or header == expected:
            return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "Требуется авторизация UI."})

    return bootstrap


def register_ui_session_route(app: FastAPI) -> None:
    @app.post("/api/ui/session")
    def establish_ui_session(request: Request) -> Response:
        if not ui_auth_enabled():
            return JSONResponse({"ok": True})
        bootstrap_hdr = (request.headers.get("x-slysh-bootstrap") or "").strip()
        expected_boot = getattr(app.state, "ui_bootstrap_token", None)
        if bootstrap_hdr != expected_boot:
            return JSONResponse(status_code=401, content={"detail": "Недопустимый bootstrap UI."})
        session = getattr(app.state, "ui_auth_token", "")
        resp = JSONResponse({"ok": True})
        set_ui_session_cookie(resp, session, cookie_name=ui_cookie_name(app))
        return resp


def inject_bootstrap_index(app: FastAPI, index_path: Path) -> None:
    """Serve index.html with one-time bootstrap token for WebView (before pywebview.api is ready)."""

    @app.get("/")
    def spa_index() -> Response:
        if not ui_auth_enabled() or not bootstrap_in_html_enabled():
            return FileResponse(index_path)
        token = str(getattr(app.state, "ui_bootstrap_token", "") or "")
        html = index_path.read_text(encoding="utf-8")
        snippet = (
            "<script>window.__SLYSH_BOOTSTRAP__="
            f"{json.dumps(token)};</script>"
        )
        if "<head>" in html:
            html = html.replace("<head>", f"<head>{snippet}", 1)
        else:
            html = snippet + html
        return HTMLResponse(
            html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


def set_ui_session_cookie(
    response: Response,
    token: str,
    *,
    cookie_name: str = _DEFAULT_COOKIE,
) -> None:
    response.set_cookie(
        cookie_name,
        token,
        httponly=True,
        samesite="strict",
        secure=False,
    )
