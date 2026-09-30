from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from slysh.engine_auth import engine_auth_headers


class EngineError(Exception):
    """Raised when the engine HTTP API returns an error body."""


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _error_message(exc: HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or str(exc)
    if isinstance(data, dict):
        for key in ("error", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return raw.strip() or str(exc)


def _get(base_url: str, path: str) -> dict:
    req = Request(_url(base_url, path), headers=engine_auth_headers())
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(base_url: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    headers.update(engine_auth_headers())
    req = Request(
        _url(base_url, path),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=None) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise EngineError(_error_message(exc)) from exc
    except URLError as exc:
        raise EngineError(str(exc.reason or exc)) from exc


def health(base_url: str) -> dict:
    return _get(base_url, "/health")


def progress(base_url: str) -> dict:
    return _get(base_url, "/progress")


def transcribe_file(
    base_url: str,
    path: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> dict:
    payload: dict = {"path": path}
    if start_ms is not None:
        payload["start_ms"] = start_ms
    if end_ms is not None:
        payload["end_ms"] = end_ms
    return _post(base_url, "/transcribe_file", payload)


def transcribe_chunk(base_url: str, samples: list[float]) -> dict:
    return _post(base_url, "/transcribe_chunk", {"samples": samples})


def cancel(base_url: str) -> dict:
    return _post(base_url, "/cancel")
