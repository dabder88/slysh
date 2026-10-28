"""User-facing YouTube ingest error messages (no tracebacks in UI)."""

from __future__ import annotations

import json
import re
from typing import Any

_MAX_MESSAGE = 600
_MAX_DETAIL = 500

_PROXY_HINT = "Настройки → Сеть: включите прокси и отметьте цель «YouTube»."
_APIFY_HINT = "На экране YouTube выберите способ «Облачный сервис (Apify)» и укажите API-ключ."
_COOKIES_HINT = "Войдите в YouTube в Firefox и извлеките cookies на экране YouTube."


def _strip_traceback(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if "Traceback (most recent call last)" in raw:
        lines = raw.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("Traceback"):
                continue
            if line and not line.startswith(" ") and not line.startswith("File "):
                return line.strip()
        return lines[-1].strip() if lines else raw[:_MAX_MESSAGE]
    return raw[:_MAX_MESSAGE]


def _classify(text: str) -> str:
    lower = text.lower()
    if "requestblocked" in lower or "blocked requests from your ip" in lower:
        return "ip_blocked"
    if "sign in to confirm" in lower or "not a bot" in lower:
        return "auth_required"
    if "po token" in lower:
        return "auth_required"
    if "субтитры не найдены" in lower or "no subtitles" in lower or "transcript" in lower and "not found" in lower:
        return "no_subtitles"
    if any(
        needle in lower
        for needle in (
            "timeout",
            "timed out",
            "таймаут",
            "unable to download",
            "connection refused",
            "name or service not known",
            "network is unreachable",
            "failed to establish a new connection",
            "http error 403",
            "403 forbidden",
            "getaddrinfo failed",
            "errno 110",
            "errno 111",
        )
    ):
        return "geo_or_network"
    return "generic"


def _hints_for_code(code: str, *, method: str | None = None) -> list[str]:
    method_key = (method or "").strip().lower()
    hints: list[str] = []
    if code == "geo_or_network":
        hints.append(
            "YouTube может быть недоступен из вашей сети. "
            f"{_PROXY_HINT}"
        )
        hints.append("Проверьте VPN или другой прокси-сервер с доступом к YouTube.")
        if method_key == "ytdlp":
            hints.append(_APIFY_HINT)
    elif code == "ip_blocked":
        hints.append(
            "YouTube временно блокирует запросы с вашего IP (часто у прокси или VPS)."
        )
        hints.append(_APIFY_HINT)
        hints.append(f"Смените прокси или {_PROXY_HINT}")
    elif code == "auth_required":
        hints.append(_COOKIES_HINT)
        hints.append(_APIFY_HINT)
    elif code == "no_subtitles":
        hints.append("У видео может не быть субтитров — попробуйте другое видео.")
        hints.append(_APIFY_HINT)
    elif code == "timeout":
        hints.append(
            "Запрос к YouTube занял слишком много времени. "
            f"{_PROXY_HINT}"
        )
        hints.append(_APIFY_HINT)
    else:
        hints.append(_APIFY_HINT)
        hints.append(_PROXY_HINT)
    return hints


def format_youtube_failure(
    exc_or_text: BaseException | str,
    *,
    method: str | None = None,
) -> dict[str, Any]:
    if isinstance(exc_or_text, BaseException):
        text = str(exc_or_text)
    else:
        text = str(exc_or_text or "")
    clean = _strip_traceback(text)
    code = _classify(clean)
    if isinstance(exc_or_text, TimeoutError) or "wall-clock" in clean.lower():
        code = "timeout"
    message = clean or "Не удалось получить транскрипт YouTube."
    if code == "geo_or_network" and "прокси" not in message.lower():
        message = (
            "Не удалось связаться с YouTube (сеть или блокировка региона). "
            + message
        )
    elif code == "ip_blocked":
        message = (
            "YouTube отклонил запрос с вашего IP. "
            "Локальный fallback через youtube-transcript-api не сработал."
        )
    elif code == "timeout":
        message = "Превышено время ожидания ответа от YouTube."
    message = message[:_MAX_MESSAGE]
    hints = _hints_for_code(code, method=method)
    detail = text[:_MAX_DETAIL] if len(text) > len(message) + 20 else ""
    return {
        "code": code,
        "message": message,
        "hints": hints,
        "detail": detail,
    }


def parse_subprocess_error_json(stderr: str) -> str | None:
    """Parse one-line JSON {\"error\": \"...\"} from subprocess stderr."""
    for line in reversed((stderr or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    return None
