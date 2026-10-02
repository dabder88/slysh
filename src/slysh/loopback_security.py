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


def _request_port(request: Request) -> int:
    port = request.url.port
    if port is not None:
        return port
    scheme = (request.url.scheme or "http").lower()
    return 443 if scheme == "https" else 80


def _allowed_hosts(request: Request) -> set[str]:
    port = _request_port(request)
    hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    }
    if os.environ.get("PYTEST_CURRENT_TEST"):
        hosts.update({"testserver", "127.0.0.1", "localhost", "[::1]"})
    return hosts


def _allowed_origins(request: Request) -> set[str]:
    port = _request_port(request)
    origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    }
    if os.environ.get("PYTEST_CURRENT_TEST"):
        origins.add("http://testserver")
    return origins


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
            allowed = _allowed_origins(request)
            origin = (request.headers.get("origin") or "").strip().rstrip("/")
            if origin:
                if origin not in allowed:
                    return JSONResponse(status_code=403, content={"detail": "Недопустимый Origin."})
            else:
                referer = (request.headers.get("referer") or "").strip()
                if not referer or not any(
                    referer.startswith(f"{base}/") or referer == base for base in allowed
                ):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Требуется Origin или Referer с localhost."},
                    )
        return await call_next(request)
