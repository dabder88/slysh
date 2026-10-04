from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from slysh.compute import _read_settings, mutate_settings
from slysh.secrets_dpapi import clear_nested, get_nested, set_nested

OPENROUTER_DEFAULT_MODEL = "openai/whisper-1"
OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
OPENROUTER_MODELS_URL = (
    "https://openrouter.ai/api/v1/models?output_modalities=transcription"
)
CLI_GEMINI_ID = "cli:gemini"
REMOTE_BACKENDS = frozenset({"openrouter", "custom", "cli", "http"})
LOCAL_BACKENDS = frozenset({"gigaam", "whisper"})
STT_PROTOCOLS = frozenset({"openai", "gladia", "deepgram"})
REMOTE_ID_PREFIXES = ("openrouter:", "custom:", "cli:", "http:")

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class HttpPreset:
    id: str
    name: str
    protocol: str
    endpoint: str
    default_model: str
    models: tuple[str, ...]
    env_key: str
    hint: str
    key_placeholder: str


HTTP_PRESETS: tuple[HttpPreset, ...] = (
    HttpPreset(
        id="groq",
        name="Groq",
        protocol="openai",
        endpoint="https://api.groq.com/openai/v1",
        default_model="whisper-large-v3-turbo",
        models=(
            "whisper-large-v3-turbo",
            "whisper-large-v3",
            "distil-whisper-large-v3-en",
        ),
        env_key="GROQ_API_KEY",
        hint="Ключ из console.groq.com. Совместим с OpenAI Whisper API.",
        key_placeholder="gsk_…",
    ),
    HttpPreset(
        id="openai",
        name="OpenAI",
        protocol="openai",
        endpoint="https://api.openai.com/v1",
        default_model="whisper-1",
        models=("whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"),
        env_key="OPENAI_API_KEY",
        hint="Ключ из platform.openai.com. Endpoint /v1/audio/transcriptions.",
        key_placeholder="sk-…",
    ),
    HttpPreset(
        id="gladia",
        name="Gladia",
        protocol="gladia",
        endpoint="https://api.gladia.io",
        default_model="solaria-1",
        models=("solaria-1", "solaria-3"),
        env_key="GLADIA_API_KEY",
        hint="Ключ из app.gladia.io. Для русского выбирайте solaria-1: solaria-3 только en/fr/de/es/it.",
        key_placeholder="ключ Gladia",
    ),
    HttpPreset(
        id="deepgram",
        name="Deepgram",
        protocol="deepgram",
        endpoint="https://api.deepgram.com",
        default_model="nova-3",
        models=("nova-3", "nova-2", "enhanced", "base"),
        env_key="DEEPGRAM_API_KEY",
        hint="Ключ из console.deepgram.com. Заголовок Authorization: Token.",
        key_placeholder="ключ Deepgram",
    ),
)

_PRESET_BY_ID = {item.id: item for item in HTTP_PRESETS}
_DEFAULT_ENDPOINT = {item.protocol: item.endpoint for item in HTTP_PRESETS}
_DEFAULT_MODEL = {item.protocol: item.default_model for item in HTTP_PRESETS}


def is_remote_id(model_id: str) -> bool:
    value = (model_id or "").strip()
    return value.startswith(REMOTE_ID_PREFIXES)


def backend_for_id(model_id: str) -> str:
    value = (model_id or "").strip()
    if value.startswith("openrouter:"):
        return "openrouter"
    if value.startswith("custom:"):
        return "custom"
    if value.startswith("http:"):
        return "http"
    if value.startswith("cli:"):
        return "cli"
    if value.startswith("whisper:"):
        return "whisper"
    return "gigaam"


def get_http_preset(preset_id: str) -> HttpPreset | None:
    return _PRESET_BY_ID.get(str(preset_id or "").strip())


def default_endpoint_for_protocol(protocol: str) -> str:
    return _DEFAULT_ENDPOINT.get(str(protocol or "").strip(), "")


def default_model_for_protocol(protocol: str) -> str:
    return _DEFAULT_MODEL.get(str(protocol or "").strip(), "")


def normalize_protocol(protocol: str | None) -> str:
    value = str(protocol or "openai").strip().lower() or "openai"
    if value not in STT_PROTOCOLS:
        raise ValueError("Неизвестный тип API. Доступны: OpenAI, Gladia, Deepgram.")
    return value


def mask_secret_preview(value: str | None, *, head: int = 4, tail: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= head + tail + 1:
        if len(text) <= 4:
            return "…"
        return text[:2] + "…" + text[-2:]
    return text[:head] + "…" + text[-tail:]


def mask_secret(value: str | None) -> str:
    return mask_secret_preview(value)


def _public_key_fields(key: str) -> dict:
    masked = mask_secret_preview(key)
    return {
        "api_key_set": bool(key),
        "api_key_masked": masked,
        "api_key_tail": masked,
    }


def normalize_stt_endpoint(endpoint: str) -> str:
    url = str(endpoint or "").strip().rstrip("/")
    if not url:
        raise ValueError("Нужен endpoint.")
    lower = url.lower()
    if lower.endswith("/audio/transcriptions") or lower.endswith("/transcriptions"):
        return url
    return url + "/audio/transcriptions"


def _providers_block() -> dict:
    data = _read_settings().get("providers")
    return dict(data) if isinstance(data, dict) else {}


def _save_providers(block: dict) -> None:
    def patch(data: dict) -> None:
        data["providers"] = block

    mutate_settings(patch)


def _secret_key_path(*parts: str) -> tuple[str, ...]:
    return ("providers", *parts)


def _read_stored_api_key(*path_parts: str) -> str:
    stored = get_nested(_secret_key_path(*path_parts, "api_key"))
    if stored:
        return stored
    block_name = path_parts[0]
    if len(path_parts) == 1:
        raw = _providers_block().get(block_name)
    elif block_name == "custom" and len(path_parts) == 2:
        raw = next(
            (
                item
                for item in (_providers_block().get("custom") or [])
                if isinstance(item, dict) and str(item.get("id") or "") == path_parts[1]
            ),
            None,
        )
    else:
        http = _http_block()
        raw = http.get(path_parts[1])
    if not isinstance(raw, dict):
        return ""
    plain = str(raw.get("api_key") or "").strip()
    if not plain:
        return ""
    set_nested(_secret_key_path(*path_parts, "api_key"), plain)
    data = dict(raw)
    data.pop("api_key", None)
    if len(path_parts) == 1:
        block = _providers_block()
        block[block_name] = data
        _save_providers(block)
    elif block_name == "custom" and len(path_parts) == 2:
        block = _providers_block()
        items = block.get("custom")
        if isinstance(items, list):
            cid = path_parts[1]
            block["custom"] = [
                data if isinstance(row, dict) and str(row.get("id") or "") == cid else row
                for row in items
            ]
            _save_providers(block)
    else:
        block = _providers_block()
        http = dict(block.get("http") or {})
        http[path_parts[1]] = data
        block["http"] = http
        _save_providers(block)
    return plain


def _write_stored_api_key(*path_parts: str, value: str | None) -> None:
    if value is None:
        return
    key_path = _secret_key_path(*path_parts, "api_key")
    text = str(value).strip()
    if text:
        set_nested(key_path, text)
    else:
        clear_nested(key_path)
    if len(path_parts) == 1:
        block = _providers_block()
        current = block.get(path_parts[0])
        data = dict(current) if isinstance(current, dict) else {}
        data.pop("api_key", None)
        block[path_parts[0]] = data
        _save_providers(block)
    elif path_parts[0] == "custom" and len(path_parts) == 2:
        block = _providers_block()
        items = block.get("custom")
        if isinstance(items, list):
            cid = path_parts[1]
            new_items = []
            for row in items:
                if not isinstance(row, dict) or str(row.get("id") or "") != cid:
                    new_items.append(row)
                    continue
                data = dict(row)
                data.pop("api_key", None)
                new_items.append(data)
            block["custom"] = new_items
            _save_providers(block)
    else:
        block = _providers_block()
        http = dict(block.get("http") or {})
        current = http.get(path_parts[1])
        data = dict(current) if isinstance(current, dict) else {}
        data.pop("api_key", None)
        http[path_parts[1]] = data
        block["http"] = http
        _save_providers(block)


def openrouter_api_key() -> str:
    env = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if env:
        return env
    return _read_stored_api_key("openrouter")


def openrouter_model() -> str:
    raw = _providers_block().get("openrouter")
    if isinstance(raw, dict):
        model = str(raw.get("model") or "").strip()
        if model:
            return model
    return OPENROUTER_DEFAULT_MODEL


def openrouter_cached_models() -> list[dict]:
    raw = _providers_block().get("openrouter")
    if not isinstance(raw, dict):
        return []
    items = raw.get("models")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        out.append(
            {
                "id": model_id,
                "label": str(item.get("label") or model_id).strip() or model_id,
            }
        )
    return out


def save_openrouter(
    api_key: str | None = None,
    model: str | None = None,
    models: list[dict] | None = None,
) -> dict:
    block = _providers_block()
    current = block.get("openrouter")
    data = dict(current) if isinstance(current, dict) else {}
    if api_key is not None:
        _write_stored_api_key("openrouter", value=str(api_key))
    if model is not None:
        value = str(model).strip()
        data["model"] = value or OPENROUTER_DEFAULT_MODEL
    if models is not None:
        data["models"] = models
    block["openrouter"] = data
    _save_providers(block)
    return public_openrouter()


def public_openrouter() -> dict:
    key = openrouter_api_key()
    return {
        **_public_key_fields(key),
        "model": openrouter_model(),
        "models": openrouter_cached_models(),
    }


def apify_api_key() -> str:
    env = (os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN") or "").strip()
    if env:
        return env
    return _read_stored_api_key("apify")


def save_apify(api_key: str | None = None) -> dict:
    block = _providers_block()
    current = block.get("apify")
    data = dict(current) if isinstance(current, dict) else {}
    if api_key is not None:
        _write_stored_api_key("apify", value=str(api_key))
    block["apify"] = data
    _save_providers(block)
    return public_apify()


def public_apify() -> dict:
    key = apify_api_key()
    return _public_key_fields(key)


def _http_block() -> dict:
    raw = _providers_block().get("http")
    return dict(raw) if isinstance(raw, dict) else {}


def http_api_key(preset_id: str) -> str:
    preset = get_http_preset(preset_id)
    if preset is None:
        return ""
    env = (os.environ.get(preset.env_key) or "").strip()
    if env:
        return env
    return _read_stored_api_key("http", preset.id)


def http_model(preset_id: str) -> str:
    preset = get_http_preset(preset_id)
    if preset is None:
        return ""
    raw = _http_block().get(preset.id)
    if isinstance(raw, dict):
        model = str(raw.get("model") or "").strip()
        if model:
            return model
    return preset.default_model


def get_http_config(preset_id: str) -> dict | None:
    preset = get_http_preset(preset_id)
    if preset is None:
        return None
    return {
        "id": preset.id,
        "name": preset.name,
        "protocol": preset.protocol,
        "endpoint": preset.endpoint,
        "model": http_model(preset.id),
        "api_key": http_api_key(preset.id),
    }


def _public_http_preset(preset: HttpPreset) -> dict:
    key = http_api_key(preset.id)
    model = http_model(preset.id)
    return {
        "id": preset.id,
        "name": preset.name,
        "protocol": preset.protocol,
        "endpoint": preset.endpoint,
        "model": model,
        "models": list(preset.models),
        "hint": preset.hint,
        "key_placeholder": preset.key_placeholder,
        "env_key": preset.env_key,
        **_public_key_fields(key),
        "ready": bool(key),
    }


def list_http_presets() -> list[dict]:
    return [_public_http_preset(item) for item in HTTP_PRESETS]


def save_http_preset(
    preset_id: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    preset = get_http_preset(preset_id)
    if preset is None:
        raise ValueError("Неизвестный сервис.")
    block = _providers_block()
    http = dict(block.get("http") or {}) if isinstance(block.get("http"), dict) else {}
    current = http.get(preset.id)
    data = dict(current) if isinstance(current, dict) else {}
    if api_key is not None:
        _write_stored_api_key("http", preset.id, value=str(api_key))
    if model is not None:
        value = str(model).strip()
        data["model"] = value or preset.default_model
    http[preset.id] = data
    block["http"] = http
    _save_providers(block)
    return _public_http_preset(preset)


def _slug_id(name: str) -> str:
    base = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return base or uuid.uuid4().hex[:8]


def list_custom_providers() -> list[dict]:
    raw = _providers_block().get("custom")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        protocol = str(item.get("protocol") or "openai").strip().lower() or "openai"
        if protocol not in STT_PROTOCOLS:
            protocol = "openai"
        out.append(
            {
                "id": cid,
                "name": str(item.get("name") or cid).strip() or cid,
                "protocol": protocol,
                "endpoint": str(item.get("endpoint") or "").strip(),
                "model": str(item.get("model") or "").strip(),
                "api_key": custom_api_key(cid),
            }
        )
    return out


def custom_api_key(provider_id: str) -> str:
    return _read_stored_api_key("custom", str(provider_id or "").strip())


def get_custom_provider(provider_id: str) -> dict | None:
    wanted = str(provider_id or "").strip()
    for item in list_custom_providers():
        if item["id"] == wanted:
            return item
    return None


def custom_is_ready(item: dict) -> bool:
    protocol = str(item.get("protocol") or "openai")
    endpoint = str(item.get("endpoint") or "").strip()
    model = str(item.get("model") or "").strip()
    key = str(item.get("api_key") or "").strip()
    if protocol == "openai":
        return bool(endpoint and model)
    return bool(endpoint and key)


def _public_custom(item: dict) -> dict:
    key = custom_api_key(str(item.get("id") or ""))
    protocol = str(item.get("protocol") or "openai")
    row = {**item, "api_key": key}
    return {
        "id": item["id"],
        "name": item["name"],
        "protocol": protocol,
        "endpoint": item["endpoint"],
        "model": item["model"],
        **_public_key_fields(key),
        "ready": custom_is_ready(row),
    }


def upsert_custom_provider(
    *,
    provider_id: str | None,
    name: str,
    endpoint: str,
    model: str,
    api_key: str | None = None,
    keep_key: bool = False,
    protocol: str | None = None,
) -> dict:
    title = str(name or "").strip()
    if not title:
        raise ValueError("Нужно имя провайдера.")
    kind = normalize_protocol(protocol)
    url = str(endpoint or "").strip() or default_endpoint_for_protocol(kind)
    if not url:
        raise ValueError("Нужен endpoint.")
    model_id = str(model or "").strip() or default_model_for_protocol(kind)
    if kind == "openai":
        if not model_id:
            raise ValueError("Нужна модель.")
        normalize_stt_endpoint(url)
    items = list_custom_providers()
    cid = str(provider_id or "").strip() or _slug_id(title)
    existing = next((item for item in items if item["id"] == cid), None)
    if api_key is not None:
        _write_stored_api_key("custom", cid, value=str(api_key))
    elif not keep_key and existing is None:
        _write_stored_api_key("custom", cid, value="")
    row = {
        "id": cid,
        "name": title,
        "protocol": kind,
        "endpoint": url,
        "model": model_id,
    }
    if existing is None:
        items.append(row)
    else:
        items = [row if item["id"] == cid else item for item in items]
    block = _providers_block()
    block["custom"] = items
    _save_providers(block)
    return _public_custom(row)


def delete_custom_provider(provider_id: str) -> bool:
    wanted = str(provider_id or "").strip()
    items = list_custom_providers()
    kept = [item for item in items if item["id"] != wanted]
    if len(kept) == len(items):
        return False
    block = _providers_block()
    block["custom"] = kept
    _save_providers(block)
    return True


def find_gemini_binary(which: Callable[[str], str | None] | None = None) -> str | None:
    lookup = which or shutil.which
    raw = _providers_block().get("cli")
    if isinstance(raw, dict):
        gemini = raw.get("gemini")
        if isinstance(gemini, dict):
            configured = str(gemini.get("bin") or "").strip()
            if configured:
                from pathlib import Path

                path = Path(configured)
                if path.is_file():
                    return str(path)
    found = lookup("gemini")
    return str(found) if found else None


def gemini_status(which: Callable[[str], str | None] | None = None) -> dict:
    path = find_gemini_binary(which=which)
    return {"found": bool(path), "path": path or ""}


def any_remote_ready(which: Callable[[str], str | None] | None = None) -> bool:
    if openrouter_api_key():
        return True
    for preset in HTTP_PRESETS:
        if http_api_key(preset.id):
            return True
    for item in list_custom_providers():
        if custom_is_ready(item):
            return True
    return bool(find_gemini_binary(which=which))


def migrate_legacy_provider_secrets() -> None:
    """Move plaintext provider keys from settings.json into DPAPI (idempotent)."""
    from slysh.settings_store import sync_settings_backup_from_primary

    openrouter_api_key()
    apify_api_key()
    for preset in HTTP_PRESETS:
        http_api_key(preset.id)
    for item in list_custom_providers():
        cid = str(item.get("id") or "").strip()
        if cid:
            custom_api_key(cid)
    sync_settings_backup_from_primary()


def public_providers(which: Callable[[str], str | None] | None = None) -> dict:
    return {
        "openrouter": public_openrouter(),
        "apify": public_apify(),
        "http": list_http_presets(),
        "custom": [_public_custom(item) for item in list_custom_providers()],
        "cli": {"gemini": gemini_status(which=which)},
        "remote_ready": any_remote_ready(which=which),
    }


def parse_openrouter_models(payload: Any) -> list[dict]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        out.append(
            {
                "id": model_id,
                "label": str(item.get("name") or model_id).strip() or model_id,
            }
        )
    return out
