from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

DEFAULT_BATCH_RULES: dict[str, Any] = {
    "batch_type": "file",
    "speakers": False,
    "export": False,
    "export_fmt": "srt",
    "export_dir_mode": "beside_source",
    "export_dir": "",
    "export_dirs": [],
    "skip_completed": True,
    "on_error": "continue",
    "youtube_method": "apify",
    "youtube_language": "ru",
    "delay_seconds": 5,
}


def normalize_rules(raw: dict[str, Any] | None) -> dict[str, Any]:
    rules = deepcopy(DEFAULT_BATCH_RULES)
    if not raw:
        return rules
    for key in DEFAULT_BATCH_RULES:
        if key in raw:
            rules[key] = raw[key]
    if rules["batch_type"] not in {"file", "youtube"}:
        rules["batch_type"] = "file"
    if rules["export_dir_mode"] not in {"beside_source", "fixed"}:
        rules["export_dir_mode"] = "beside_source"
    if rules["export_fmt"] not in {"srt", "vtt", "txt", "md"}:
        rules["export_fmt"] = "srt"
    method = str(rules.get("youtube_method") or "apify").strip().lower()
    rules["youtube_method"] = method if method in {"apify", "ytdlp"} else "apify"
    try:
        rules["delay_seconds"] = max(0, int(rules.get("delay_seconds", 5)))
    except (TypeError, ValueError):
        rules["delay_seconds"] = 5
    lang = str(rules.get("youtube_language") or "ru").strip()
    rules["youtube_language"] = lang or "ru"
    raw_dirs = rules.get("export_dirs")
    if isinstance(raw_dirs, list):
        rules["export_dirs"] = [str(d).strip() for d in raw_dirs if str(d).strip()]
    else:
        rules["export_dirs"] = []
    if rules["batch_type"] == "youtube":
        rules["speakers"] = False
    return rules


def is_youtube_batch_rules(rules: dict[str, Any] | None) -> bool:
    normalized = normalize_rules(rules)
    return normalized.get("batch_type") == "youtube"


def rules_to_json(rules: dict[str, Any] | None) -> str:
    return json.dumps(normalize_rules(rules), ensure_ascii=False)


def rules_from_json(text: str | None) -> dict[str, Any]:
    if not text:
        return normalize_rules(None)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return normalize_rules(None)
    if not isinstance(data, dict):
        return normalize_rules(None)
    return normalize_rules(data)
