from __future__ import annotations

from slysh.providers import mask_secret_preview


def test_mask_secret_preview_long():
    assert mask_secret_preview("sk-or-v1-abcdefgh") == "sk-o…efgh"


def test_mask_secret_preview_short():
    assert mask_secret_preview("abcd") == "…"
    assert mask_secret_preview("abcdef") == "ab…ef"


def test_mask_secret_preview_empty():
    assert mask_secret_preview("") == ""
    assert mask_secret_preview(None) == ""
