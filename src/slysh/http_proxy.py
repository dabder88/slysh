from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote
from urllib.request import ProxyHandler, build_opener, urlopen

from slysh.compute import _read_settings, mutate_settings
from slysh.providers import mask_secret_preview
from slysh.secrets_dpapi import clear_nested, get_nested, set_nested

PROXY_TARGET_IDS = frozenset(
    {
        "openrouter",
        "groq",
        "openai",
        "gladia",
        "deepgram",
        "custom",
        "gemini",
        "youtube",
    }
)

_DEFAULT_TARGETS = {tid: True for tid in PROXY_TARGET_IDS}


def _default_targets() -> dict[str, bool]:
    return dict(_DEFAULT_TARGETS)


def _read_stored_proxy_password() -> str:
    stored = get_nested(("proxy", "password"))
    if stored:
        return stored
    raw = _read_settings().get("proxy")
    if not isinstance(raw, dict):
        return ""
    plain = str(raw.get("password") or "").strip()
    if not plain:
        return ""
    set_nested(("proxy", "password"), plain)

    def patch(data: dict) -> None:
        block = dict(data.get("proxy") or {})
        block.pop("password", None)
        data["proxy"] = block

    mutate_settings(patch)
    from slysh.settings_store import sync_settings_backup_from_primary

    sync_settings_backup_from_primary()
    return plain


def load_proxy_config() -> dict[str, Any]:
    raw = _read_settings().get("proxy")
    if not isinstance(raw, dict):
        return {
            "enabled": False,
            "host": "",
            "port": 8080,
            "username": "",
            "password": "",
            "targets": _default_targets(),
        }
    targets = raw.get("targets")
    merged = _default_targets()
    if isinstance(targets, dict):
        for key in PROXY_TARGET_IDS:
            if key in targets:
                merged[key] = bool(targets[key])
    port = raw.get("port")
    try:
        port_int = int(port) if port is not None else 8080
    except (TypeError, ValueError):
        port_int = 8080
    return {
        "enabled": bool(raw.get("enabled")),
        "host": str(raw.get("host") or "").strip(),
        "port": port_int,
        "username": str(raw.get("username") or ""),
        "password": _read_stored_proxy_password(),
        "targets": merged,
    }


def _validate_proxy_config(config: dict[str, Any]) -> None:
    if not config.get("enabled"):
        return
    host = str(config.get("host") or "").strip()
    if not host:
        raise ValueError("Укажите хост прокси.")
    port = config.get("port")
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        raise ValueError("Некорректный порт прокси.") from None
    if port_int < 1 or port_int > 65535:
        raise ValueError("Порт прокси должен быть от 1 до 65535.")


def save_proxy_config(
    *,
    enabled: bool | None = None,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    keep_password: bool = False,
    targets: dict[str, bool] | None = None,
) -> dict[str, Any]:
    current = load_proxy_config()
    if enabled is not None:
        current["enabled"] = bool(enabled)
    if host is not None:
        current["host"] = str(host).strip()
    if port is not None:
        current["port"] = int(port)
    if username is not None:
        current["username"] = str(username)
    if password is not None:
        text = str(password)
        if text:
            set_nested(("proxy", "password"), text)
            current["password"] = text
        else:
            clear_nested(("proxy", "password"))
            current["password"] = ""
    elif keep_password:
        current["password"] = _read_stored_proxy_password()
    if targets is not None:
        merged = dict(current["targets"])
        for key, value in targets.items():
            tid = str(key).strip()
            if tid in PROXY_TARGET_IDS:
                merged[tid] = bool(value)
        current["targets"] = merged
    _validate_proxy_config(current)
    proxy_block = {
        "enabled": current["enabled"],
        "host": current["host"],
        "port": current["port"],
        "username": current["username"],
        "targets": current["targets"],
    }

    def patch(data: dict) -> None:
        data["proxy"] = proxy_block

    mutate_settings(patch)
    return current


def public_proxy_config() -> dict[str, Any]:
    cfg = load_proxy_config()
    pwd = cfg["password"]
    masked = mask_secret_preview(pwd) if pwd else ""
    return {
        "enabled": cfg["enabled"],
        "host": cfg["host"],
        "port": cfg["port"],
        "username": cfg["username"],
        "password": "",
        "password_set": bool(pwd),
        "password_masked": masked,
        "targets": dict(cfg["targets"]),
    }


def migrate_proxy_secret() -> None:
    from slysh.settings_store import sync_settings_backup_from_primary

    _read_stored_proxy_password()
    sync_settings_backup_from_primary()


def build_proxy_url(config: dict[str, Any] | None = None) -> str:
    cfg = config if config is not None else load_proxy_config()
    host = str(cfg.get("host") or "").strip()
    if not host:
        return ""
    try:
        port = int(cfg.get("port") or 0)
    except (TypeError, ValueError):
        return ""
    if port < 1 or port > 65535:
        return ""
    user = str(cfg.get("username") or "").strip()
    pwd = str(cfg.get("password") or "")
    if user or pwd:
        auth = f"{quote(user, safe='')}:{quote(pwd, safe='')}@"
    else:
        auth = ""
    return f"http://{auth}{host}:{port}"


def proxy_target_for_request(backend: str, model_id: str) -> str | None:
    b = str(backend or "").strip().lower()
    mid = str(model_id or "").strip()
    if b == "openrouter":
        return "openrouter"
    if b == "http":
        if mid.startswith("http:"):
            preset = mid.split(":", 1)[1]
            return preset if preset in PROXY_TARGET_IDS else None
        return mid if mid in PROXY_TARGET_IDS else None
    if b == "custom":
        return "custom"
    if b == "cli":
        return "gemini"
    return None


def should_use_proxy_for_target(target_id: str) -> bool:
    tid = str(target_id or "").strip()
    if tid not in PROXY_TARGET_IDS:
        return False
    cfg = load_proxy_config()
    if not cfg.get("enabled"):
        return False
    if not cfg["targets"].get(tid):
        return False
    return bool(build_proxy_url(cfg))


def should_use_proxy(backend: str, model_id: str) -> bool:
    target = proxy_target_for_request(backend, model_id)
    if not target:
        return False
    return should_use_proxy_for_target(target)


def proxy_config_error_for_target(target_id: str) -> str | None:
    tid = str(target_id or "").strip()
    if tid not in PROXY_TARGET_IDS:
        return None
    cfg = load_proxy_config()
    if not cfg.get("enabled") or not cfg["targets"].get(tid):
        return None
    if not str(cfg.get("host") or "").strip():
        return "Прокси включён для этого сервиса, но хост не задан. Откройте настройки."
    try:
        port = int(cfg.get("port"))
        if port < 1 or port > 65535:
            raise ValueError
    except (TypeError, ValueError):
        return "Прокси включён для этого сервиса, но порт некорректен. Откройте настройки."
    return None


def proxy_config_error_if_required(backend: str, model_id: str) -> str | None:
    target = proxy_target_for_request(backend, model_id)
    if not target:
        return None
    return proxy_config_error_for_target(target)


def opener_for_target(target_id: str) -> Callable[..., Any]:
    from slysh.remote_asr import RemoteAsrError

    err = proxy_config_error_for_target(target_id)
    if err:
        raise RemoteAsrError(err)
    if not should_use_proxy_for_target(target_id):
        return urlopen
    proxy_url = build_proxy_url()
    if not proxy_url:
        return urlopen
    handler = ProxyHandler({"http": proxy_url, "https": proxy_url})
    return build_opener(handler).open


def opener_for_remote(backend: str, model_id: str) -> Callable[..., Any]:
    target = proxy_target_for_request(backend, model_id)
    if not target:
        return urlopen
    return opener_for_target(target)


def requests_proxies_for_target(target_id: str) -> dict[str, str]:
    err = proxy_config_error_for_target(target_id)
    if err:
        from slysh.remote_asr import RemoteAsrError

        raise RemoteAsrError(err)
    if not should_use_proxy_for_target(target_id):
        return {}
    proxy_url = build_proxy_url()
    if not proxy_url:
        return {}
    return {"http": proxy_url, "https": proxy_url}


def subprocess_env_for_target(
    target_id: str,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    from slysh.remote_asr import RemoteAsrError

    err = proxy_config_error_for_target(target_id)
    if err:
        raise RemoteAsrError(err)
    env = dict(base if base is not None else os.environ)
    if not should_use_proxy_for_target(target_id):
        return env
    proxy_url = build_proxy_url()
    if proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = proxy_url
    return env
