"""Mirror of web/js/shell.js filterLocalModelsForUi for EN GigaAM download row."""

from __future__ import annotations

GIGAAM_MODEL_ID = "gigaam"


def filter_local_models_for_ui(items: list[dict], locale: str) -> list[dict]:
    if locale != "en":
        return list(items)
    return [
        item
        for item in items
        if not (
            item.get("id") == GIGAAM_MODEL_ID
            and item.get("ready") is False
            and item.get("downloadable") is True
        )
    ]


def test_en_hides_gigaam_download_only():
    items = [
        {
            "id": "gigaam",
            "kind": "local",
            "ready": False,
            "downloadable": True,
        },
        {"id": "whisper:base", "kind": "local", "ready": False, "downloadable": True},
        {"id": "gigaam", "kind": "local", "ready": True, "downloadable": False},
    ]
    out = filter_local_models_for_ui(items, "en")
    assert len(out) == 2
    assert out[0]["id"] == "whisper:base"
    assert out[1]["ready"] is True


def test_ru_keeps_gigaam_download():
    items = [
        {"id": "gigaam", "kind": "local", "ready": False, "downloadable": True},
    ]
    assert len(filter_local_models_for_ui(items, "ru")) == 1
