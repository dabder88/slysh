from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from slysh.chunking import offset_segments
from slysh.decode import (
    DecodeError,
    prepare_stt_chunks,
    remote_file_chunk_ms,
)
from slysh.models import Segment
from slysh.http_proxy import opener_for_remote
from slysh.providers import (
    OPENROUTER_STT_URL,
    custom_is_ready,
    get_custom_provider,
    get_http_config,
    normalize_stt_endpoint,
    openrouter_api_key,
    openrouter_model,
    parse_openrouter_models,
)

UrlOpen = Callable[..., Any]


class RemoteAsrError(Exception):
    """Raised when a remote STT provider fails."""


def _audio_content_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".wav", ".wave"}:
        return "audio/wav"
    if suffix in {".mp3", ".mpeg", ".mpga"}:
        return "audio/mpeg"
    if suffix in {".ogg", ".oga"}:
        return "audio/ogg"
    if suffix == ".webm":
        return "audio/webm"
    return "application/octet-stream"


def _seconds_to_ms(value: Any) -> int | None:
    try:
        return int(float(value) * 1000)
    except (TypeError, ValueError):
        return None


def parse_transcription_payload(data: Any, duration_ms: int) -> list[Segment]:
    if not isinstance(data, dict):
        return []
    raw_segments = data.get("segments")
    if isinstance(raw_segments, list) and raw_segments:
        out: list[Segment] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            try:
                if "start_ms" in item or "end_ms" in item:
                    start_ms = int(float(item.get("start_ms", item.get("start") or 0)))
                    end_ms = int(float(item.get("end_ms", item.get("end") or start_ms)))
                else:
                    start_ms = int(float(item.get("start") or 0) * 1000)
                    end_ms = int(float(item.get("end") or 0) * 1000)
            except (TypeError, ValueError):
                continue
            if end_ms < start_ms:
                end_ms = start_ms
            out.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
        if out:
            return out
    text = str(data.get("text") or data.get("response") or "").strip()
    if not text:
        return []
    return [Segment(0, max(int(duration_ms), 1), text)]


def parse_gladia_payload(data: Any, duration_ms: int) -> list[Segment]:
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    transcription = result.get("transcription") if isinstance(result, dict) else None
    if not isinstance(transcription, dict):
        transcription = data.get("transcription") if isinstance(data.get("transcription"), dict) else {}
    utterances = transcription.get("utterances") if isinstance(transcription, dict) else None
    if isinstance(utterances, list) and utterances:
        out: list[Segment] = []
        for item in utterances:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("transcript") or "").strip()
            if not text:
                continue
            start_ms = _seconds_to_ms(item.get("start"))
            end_ms = _seconds_to_ms(item.get("end"))
            if start_ms is None:
                start_ms = 0
            if end_ms is None or end_ms < start_ms:
                end_ms = start_ms
            out.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
        if out:
            return out
    text = ""
    if isinstance(transcription, dict):
        text = str(transcription.get("full_transcript") or transcription.get("text") or "").strip()
    if not text:
        text = str(data.get("text") or "").strip()
    if not text:
        return []
    return [Segment(0, max(int(duration_ms), 1), text)]


def parse_deepgram_payload(data: Any, duration_ms: int) -> list[Segment]:
    if not isinstance(data, dict):
        return []
    results = data.get("results") if isinstance(data.get("results"), dict) else data
    utterances = results.get("utterances") if isinstance(results, dict) else None
    if isinstance(utterances, list) and utterances:
        out: list[Segment] = []
        for item in utterances:
            if not isinstance(item, dict):
                continue
            text = str(item.get("transcript") or item.get("text") or "").strip()
            if not text:
                continue
            start_ms = _seconds_to_ms(item.get("start"))
            end_ms = _seconds_to_ms(item.get("end"))
            if start_ms is None:
                start_ms = 0
            if end_ms is None or end_ms < start_ms:
                end_ms = start_ms
            out.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
        if out:
            return out
    channels = results.get("channels") if isinstance(results, dict) else None
    if isinstance(channels, list) and channels:
        first = channels[0] if isinstance(channels[0], dict) else {}
        alts = first.get("alternatives") if isinstance(first, dict) else None
        if isinstance(alts, list) and alts and isinstance(alts[0], dict):
            text = str(alts[0].get("transcript") or "").strip()
            if text:
                return [Segment(0, max(int(duration_ms), 1), text)]
    return parse_transcription_payload(data, duration_ms)


def _error_body(exc: HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or str(exc)
    if isinstance(data, dict):
        errors = data.get("validation_errors")
        if isinstance(errors, list):
            details = [str(item).strip() for item in errors if str(item).strip()]
        else:
            details = []
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            message = str(err["message"]).strip()
        else:
            message = ""
            for key in ("error", "detail", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    message = value.strip()
                    break
        if details:
            extra = "; ".join(details)
            return f"{message} {extra}".strip() if message else extra
        if message:
            return message
    return raw.strip() or str(exc)


def _headers(api_key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra or {})
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _read_json_response(raw: str) -> dict:
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RemoteAsrError("Провайдер вернул не JSON.") from exc
    if not isinstance(data, dict):
        raise RemoteAsrError("Некорректный ответ провайдера.")
    return data


def _open_request(req: Request, opener: UrlOpen, timeout: float | None) -> dict:
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RemoteAsrError(_error_body(exc)) from exc
    except URLError as exc:
        raise RemoteAsrError(str(exc.reason or exc)) from exc
    return _read_json_response(raw)


def _post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    return _open_request(req, opener, timeout)


def _get_json(
    url: str,
    headers: dict[str, str],
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    req = Request(url, headers=headers, method="GET")
    return _open_request(req, opener, timeout)


def _post_bytes(
    url: str,
    body: bytes,
    headers: dict[str, str],
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    req = Request(url, data=body, headers=headers, method="POST")
    return _open_request(req, opener, timeout)


def _post_multipart(
    url: str,
    fields: dict[str, str],
    file_path: str,
    headers: dict[str, str],
    opener: UrlOpen,
    timeout: float | None,
    *,
    file_field: str = "file",
    content_type: str | None = None,
) -> dict:
    boundary = uuid.uuid4().hex
    filename = Path(file_path).name or "audio.mp3"
    media_type = content_type or _audio_content_type(file_path)
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    file_bytes = Path(file_path).read_bytes()
    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {media_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    req = Request(
        url,
        data=body,
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    return _open_request(req, opener, timeout)


def _transcribe_openrouter_file(
    audio_path: str,
    model: str,
    api_key: str,
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    import base64

    encoded = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "input_audio": {"data": encoded, "format": "mp3"},
        "response_format": "verbose_json",
    }
    headers = _headers(
        api_key,
        {"HTTP-Referer": "https://github.com/slysh", "X-OpenRouter-Title": "Slysh"},
    )
    try:
        return _post_json(OPENROUTER_STT_URL, payload, headers, opener, timeout)
    except RemoteAsrError:
        payload.pop("response_format", None)
        return _post_json(OPENROUTER_STT_URL, payload, headers, opener, timeout)


def _transcribe_compat_file(
    audio_path: str,
    endpoint: str,
    model: str,
    api_key: str,
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    url = normalize_stt_endpoint(endpoint)
    headers = _headers(api_key)
    fields = {"model": model, "response_format": "verbose_json"}
    try:
        return _post_multipart(url, fields, audio_path, headers, opener, timeout)
    except RemoteAsrError:
        fields = {"model": model}
        return _post_multipart(url, fields, audio_path, headers, opener, timeout)


def _strip_known_suffix(url: str, suffixes: tuple[str, ...]) -> str:
    value = url.rstrip("/")
    lower = value.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return value[: -len(suffix)].rstrip("/")
    return value


def _gladia_base(endpoint: str) -> str:
    return _strip_known_suffix(
        str(endpoint or "").strip() or "https://api.gladia.io",
        ("/v2/pre-recorded", "/v2/upload", "/v2/transcription"),
    )


def _deepgram_listen_url(endpoint: str, model: str) -> str:
    base = _strip_known_suffix(
        str(endpoint or "").strip() or "https://api.deepgram.com",
        ("/v1/listen",),
    )
    if base.lower().endswith("/v1"):
        listen = f"{base}/listen"
    else:
        listen = f"{base}/v1/listen"
    query = urlencode(
        {
            "model": model,
            "smart_format": "true",
            "utterances": "true",
            "punctuate": "true",
        }
    )
    return f"{listen}?{query}"


def gladia_init_payload(audio_url: str, model: str) -> dict:
    """Body for POST /v2/pre-recorded.

    solaria-3 requires a single en/fr/de/es/it language. Slysh has no language
    picker, so that model is omitted and Gladia uses solaria-1 (auto language,
    including Russian).
    """
    payload = {"audio_url": audio_url}
    name = str(model or "").strip().lower()
    if name in {"solaria-1", "solaria-fusion"}:
        payload["model"] = name
    return payload


def _transcribe_gladia_file(
    audio_path: str,
    endpoint: str,
    model: str,
    api_key: str,
    opener: UrlOpen,
    timeout: float | None,
    cancelled: Callable[[], bool] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict:
    if not api_key:
        raise RemoteAsrError("Нет API-ключа Gladia.")
    headers = {"x-gladia-key": api_key}
    base = _gladia_base(endpoint)
    uploaded = _post_multipart(
        f"{base}/v2/upload",
        {},
        audio_path,
        headers,
        opener,
        timeout,
        file_field="audio",
    )
    audio_url = str(uploaded.get("audio_url") or "").strip()
    if not audio_url:
        raise RemoteAsrError("Gladia не вернула audio_url после загрузки.")
    payload = gladia_init_payload(audio_url, model)
    job = _post_json(f"{base}/v2/pre-recorded", payload, headers, opener, timeout)
    result_url = str(job.get("result_url") or "").strip()
    job_id = str(job.get("id") or "").strip()
    if not result_url:
        if not job_id:
            raise RemoteAsrError("Gladia не вернула id задачи.")
        result_url = f"{base}/v2/pre-recorded/{job_id}"
    deadline = time.monotonic() + float(timeout or 300)
    wait = sleeper or time.sleep
    while True:
        if cancelled and cancelled():
            return {}
        if time.monotonic() > deadline:
            raise RemoteAsrError("Gladia не успела расшифровать файл.")
        data = _get_json(result_url, headers, opener, timeout)
        status = str(data.get("status") or "").lower()
        if status in {"done", "completed", "success"}:
            return data
        if status in {"error", "failed"}:
            err = data.get("error") or data.get("message") or "ошибка Gladia"
            raise RemoteAsrError(str(err))
        wait(1.0)


def _transcribe_deepgram_file(
    audio_path: str,
    endpoint: str,
    model: str,
    api_key: str,
    opener: UrlOpen,
    timeout: float | None,
) -> dict:
    if not api_key:
        raise RemoteAsrError("Нет API-ключа Deepgram.")
    url = _deepgram_listen_url(endpoint, model or "nova-3")
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": _audio_content_type(audio_path),
    }
    return _post_bytes(url, Path(audio_path).read_bytes(), headers, opener, timeout)


def _parse_protocol_payload(protocol: str, payload: dict, duration_ms: int) -> list[Segment]:
    kind = (protocol or "openai").strip().lower() or "openai"
    if kind == "gladia":
        return parse_gladia_payload(payload, duration_ms)
    if kind == "deepgram":
        return parse_deepgram_payload(payload, duration_ms)
    return parse_transcription_payload(payload, duration_ms)


def _transcribe_protocol(
    *,
    protocol: str,
    audio_path: str,
    endpoint: str,
    model: str,
    api_key: str,
    opener: UrlOpen,
    timeout: float | None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    kind = (protocol or "openai").strip().lower() or "openai"
    if kind == "openai":
        return _transcribe_compat_file(
            audio_path, endpoint, model, api_key, opener, timeout
        )
    if kind == "gladia":
        return _transcribe_gladia_file(
            audio_path, endpoint, model, api_key, opener, timeout, cancelled
        )
    if kind == "deepgram":
        return _transcribe_deepgram_file(
            audio_path, endpoint, model, api_key, opener, timeout
        )
    raise RemoteAsrError(f"Неизвестный тип API: {protocol}")


def fetch_openrouter_stt_models(
    opener: UrlOpen | None = None,
    timeout: float = 30,
) -> list[dict]:
    from slysh.providers import OPENROUTER_MODELS_URL, save_openrouter

    headers = _headers(openrouter_api_key())
    req = Request(OPENROUTER_MODELS_URL, headers=headers, method="GET")
    open_fn = opener or opener_for_remote("openrouter", "openrouter:")
    try:
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise RemoteAsrError(_error_body(exc)) from exc
    except (URLError, json.JSONDecodeError) as exc:
        raise RemoteAsrError(str(exc)) from exc
    models = parse_openrouter_models(payload)
    save_openrouter(models=models)
    return models


def transcribe_http_file(
    *,
    backend: str,
    model_id: str,
    audio_path: str,
    duration_ms: int,
    opener: UrlOpen | None = None,
    timeout: float | None = 300,
    cancelled: Callable[[], bool] | None = None,
) -> list[Segment]:
    open_fn = opener or opener_for_remote(backend, model_id)
    if backend == "openrouter":
        slug = model_id.split(":", 1)[1] if ":" in model_id else openrouter_model()
        key = openrouter_api_key()
        if not key:
            raise RemoteAsrError("Нет API-ключа OpenRouter.")
        payload = _transcribe_openrouter_file(audio_path, slug, key, open_fn, timeout)
        return parse_transcription_payload(payload, duration_ms)
    if backend == "http":
        preset_id = model_id.split(":", 1)[1] if ":" in model_id else model_id
        row = get_http_config(preset_id)
        if row is None:
            raise RemoteAsrError("Неизвестный HTTP-сервис.")
        if not row["api_key"]:
            raise RemoteAsrError(f"Нет API-ключа {row['name']}.")
        payload = _transcribe_protocol(
            protocol=row["protocol"],
            audio_path=audio_path,
            endpoint=row["endpoint"],
            model=row["model"],
            api_key=row["api_key"],
            opener=open_fn,
            timeout=timeout,
            cancelled=cancelled,
        )
        if cancelled and cancelled():
            return []
        return _parse_protocol_payload(row["protocol"], payload, duration_ms)
    if backend == "custom":
        cid = model_id.split(":", 1)[1] if ":" in model_id else model_id
        row = get_custom_provider(cid)
        if row is None:
            raise RemoteAsrError("Кастомный провайдер не найден.")
        if not custom_is_ready(row):
            raise RemoteAsrError("У кастомного провайдера не хватает настроек.")
        protocol = row.get("protocol") or "openai"
        payload = _transcribe_protocol(
            protocol=protocol,
            audio_path=audio_path,
            endpoint=row["endpoint"],
            model=row["model"],
            api_key=row.get("api_key") or "",
            opener=open_fn,
            timeout=timeout,
            cancelled=cancelled,
        )
        if cancelled and cancelled():
            return []
        return _parse_protocol_payload(protocol, payload, duration_ms)
    raise RemoteAsrError(f"Неизвестный HTTP-бэкенд: {backend}")


def transcribe_media(
    *,
    backend: str,
    model_id: str,
    source_path: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[float], None] | None = None,
    on_segments: Callable[[list[Segment]], None] | None = None,
    opener: UrlOpen | None = None,
    cli_transcribe: Callable[..., list[Segment]] | None = None,
) -> list[Segment]:
    is_cancelled = cancelled or (lambda: False)
    chunk_ms = remote_file_chunk_ms() if on_segments is not None else None
    chunks = prepare_stt_chunks(
        source_path,
        start_ms=start_ms,
        end_ms=end_ms,
        chunk_ms=chunk_ms,
    )
    segs: list[Segment] = []
    n = len(chunks) or 1
    try:
        for index, (audio_path, offset_ms, duration_ms) in enumerate(chunks):
            if is_cancelled():
                return segs
            if backend == "cli":
                if cli_transcribe is None:
                    from slysh.gemini_cli import transcribe_gemini_file

                    piece = transcribe_gemini_file(
                        audio_path,
                        duration_ms=duration_ms,
                        cancelled=is_cancelled,
                    )
                else:
                    piece = cli_transcribe(
                        audio_path,
                        duration_ms=duration_ms,
                        cancelled=is_cancelled,
                    )
            else:
                piece = transcribe_http_file(
                    backend=backend,
                    model_id=model_id,
                    audio_path=audio_path,
                    duration_ms=duration_ms,
                    opener=opener,
                    cancelled=is_cancelled,
                )
            if offset_ms:
                piece = offset_segments(piece, start_ms=offset_ms)
            segs.extend(piece)
            if on_segments is not None and piece:
                on_segments(piece)
            if on_progress is not None:
                on_progress((index + 1) / n)
        return segs
    except DecodeError as exc:
        raise RemoteAsrError(str(exc)) from exc
    finally:
        for audio_path, _offset, _dur in chunks:
            try:
                os.remove(audio_path)
            except OSError:
                logging.debug("could not remove stt temp %s", audio_path, exc_info=True)
