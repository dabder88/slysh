"""Mirror of web/js/api.js resolveToastMessage chain lookup for locale placeholders."""

from __future__ import annotations

import json
import re
from pathlib import Path

KEY_LIKE = re.compile(r"^[a-z][\w\u0400-\u04FF]*(?:\.[\w\u0400-\u04FF]+)+$", re.I)


def _get_nested(messages: dict, key: str) -> str | None:
    parts = key.split(".")
    node: object = messages
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def resolve_toast_message(messages: dict, key: str, *, max_depth: int = 4) -> str:
    text = key
    for _ in range(max_depth):
        if not KEY_LIKE.match(text):
            break
        translated = _get_nested(messages, text)
        if not translated or translated == text:
            break
        text = translated
    return text


def test_meeting_speakers_toast_resolves_to_russian():
    ru_path = Path(__file__).resolve().parents[1] / "web" / "locales" / "ru.json"
    messages = json.loads(ru_path.read_text(encoding="utf-8"))
    resolved = resolve_toast_message(messages, "meeting.k2351323")
    assert resolved == "Распознаю спикеров…"
    assert "meeting." not in resolved
    cyrillic_key = resolve_toast_message(messages, "meeting.распознаю_спикеров")
    assert cyrillic_key == "Распознаю спикеров…"
