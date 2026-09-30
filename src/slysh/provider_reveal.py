"""Attach full API keys to provider GET payloads when UI session is valid."""
from __future__ import annotations

from typing import Any

from slysh.local_auth import ui_auth_enabled, ui_session_valid
from slysh.providers import (
    apify_api_key,
    custom_api_key,
    http_api_key,
    openrouter_api_key,
)


def should_reveal_provider_secrets(request, app) -> bool:
    if not ui_auth_enabled():
        return True
    return ui_session_valid(request, app)


def _reveal_block(block: dict[str, Any], full_key: str) -> dict[str, Any]:
    out = dict(block)
    if out.get("api_key_set") and full_key:
        out["api_key"] = full_key
    return out


def enrich_providers_payload(payload: dict[str, Any], *, reveal: bool) -> dict[str, Any]:
    if not reveal:
        return payload
    data = dict(payload)
    data["openrouter"] = _reveal_block(
        dict(data.get("openrouter") or {}),
        openrouter_api_key(),
    )
    data["apify"] = _reveal_block(dict(data.get("apify") or {}), apify_api_key())
    http_out: list[dict[str, Any]] = []
    for item in data.get("http") or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "")
        http_out.append(_reveal_block(dict(item), http_api_key(pid)))
    data["http"] = http_out
    custom_out: list[dict[str, Any]] = []
    for item in data.get("custom") or []:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "")
        custom_out.append(_reveal_block(dict(item), custom_api_key(cid)))
    data["custom"] = custom_out
    return data
