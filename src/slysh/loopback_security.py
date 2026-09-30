"""Loopback Host/Origin checks for UI API (wave D)."""
from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def loopback_strict_enabled() -> bool:
    return os.environ.get("GIGAAM_LOOPBACK_STRICT", "0") == "1"


def production_openapi_disabled() -> bool:
    return os.environ.get("SLYSH_DISABLE_OPENAPI", "0") == "1"


def _client_is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    host = (request.client.host or "").lower()
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST") and host == "testclient":
        return True
    return False


def _allowed_hosts(request: Request) -> set[str]:
    port = request.url.port
    if port is None:
        return set()
    hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    }
    if os.environ.get("PYTEST_CURRENT_TEST"):
        hosts.add("testserver")
    return hosts


def _allowed_origins(request: Request) -> set[str]:
    port = request.url.port
    if port is None:
        return set()
    return {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    }


def install_loopback_guards(app: FastAPI) -> None:
    @app.middleware("http")
    async def loopback_guard(request: Request, call_next: Callable):
        if not loopback_strict_enabled():
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if not _client_is_loopback(request):
            return JSONResponse(status_code=403, content={"detail": "Доступ только с localhost."})
        host_hdr = (request.headers.get("host") or "").strip().lower()
        if host_hdr not in _allowed_hosts(request):
            return JSONResponse(status_code=403, content={"detail": "Недопустимый Host."})
        if request.method in _MUTATING:
            origin = (request.headers.get("origin") or "").strip()
            if origin and origin.rstrip("/") not in _allowed_origins(request):
                return JSONResponse(status_code=403, content={"detail": "Недопустимый Origin."})
        return await call_next(request)
