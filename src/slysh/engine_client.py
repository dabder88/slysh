from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from slysh.engine_auth import engine_auth_headers

ENGINE_CONNECT_TIMEOUT_S = float(os.environ.get("SLYSH_ENGINE_CONNECT_TIMEOUT", "5"))
ENGINE_CONTROL_TIMEOUT_S = float(os.environ.get("SLYSH_ENGINE_CONTROL_TIMEOUT", "10"))
ENGINE_TRANSCRIBE_TIMEOUT_S = float(
    os.environ.get("SLYSH_ENGINE_TRANSCRIBE_TIMEOUT", "7200")
)


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


def _get(base_url: str, path: str, *, timeout: float | None = None) -> dict:
    req = Request(_url(base_url, path), headers=engine_auth_headers())
    connect_timeout = timeout if timeout is not None else ENGINE_CONNECT_TIMEOUT_S
    with urlopen(req, timeout=connect_timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(
    base_url: str,
    path: str,
    payload: dict | None = None,
    *,
    timeout: float | None = None,
) -> dict:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    headers.update(engine_auth_headers())
    req = Request(
        _url(base_url, path),
        data=data,
        headers=headers,
        method="POST",
    )
    effective = timeout if timeout is not None else ENGINE_CONTROL_TIMEOUT_S
    try:
        with urlopen(req, timeout=effective) as resp:
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
    from slysh.engine_watchdog import run_with_progress_watch

    payload: dict = {"path": path}
    if start_ms is not None:
        payload["start_ms"] = start_ms
    if end_ms is not None:
        payload["end_ms"] = end_ms

    def _call() -> dict:
        return _post(
            base_url,
            "/transcribe_file",
            payload,
            timeout=ENGINE_TRANSCRIBE_TIMEOUT_S,
        )

    return run_with_progress_watch(base_url, _call)


def transcribe_chunk(base_url: str, samples: list[float]) -> dict:
    return _post(
        base_url,
        "/transcribe_chunk",
        {"samples": samples},
        timeout=ENGINE_TRANSCRIBE_TIMEOUT_S,
    )


def cancel(base_url: str) -> dict:
    return _post(base_url, "/cancel", timeout=ENGINE_CONTROL_TIMEOUT_S)


def label_speakers(
    base_url: str,
    path: str,
    segments: list,
) -> dict:
    payload = {
        "path": path,
        "segments": [
            {
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text": s.text,
                "speaker": s.speaker,
            }
            for s in segments
        ],
    }
    from slysh.engine_watchdog import run_with_progress_watch

    speaker_timeout = float(os.environ.get("SLYSH_SPEAKER_HTTP_TIMEOUT", "7200"))

    def _call() -> dict:
        return _post(base_url, "/label_speakers", payload, timeout=speaker_timeout)

    return run_with_progress_watch(base_url, _call)
