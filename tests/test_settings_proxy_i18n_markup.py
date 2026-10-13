"""Settings proxy + engine install blocks must not expose bare Cyrillic UI text."""

from __future__ import annotations

import re
from pathlib import Path

from test_bento_sections_i18n_markup import _bare_cyrillic_in_section

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"


def _extract_engine_setup_block(html: str) -> str:
    m = re.search(
        r'<div id="engine-setup-settings"[^>]*>.*?</div>\s*<div id="engine-resync-settings"',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert m, "missing #engine-setup-settings"
    return m.group(0)


def _extract_proxy_pane(html: str) -> str:
    m = re.search(
        r'<div id="settings-pane-proxy"[^>]*>.*?</div>\s*<div id="settings-pane-cloud"',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert m, "missing #settings-pane-proxy"
    return m.group(0)


def test_settings_proxy_and_engine_blocks_have_no_bare_cyrillic():
    html = _INDEX.read_text(encoding="utf-8")
    all_bad: list[tuple[str, str]] = []
    for name, fragment in (
        ("engine-setup-settings", _extract_engine_setup_block(html)),
        ("settings-pane-proxy", _extract_proxy_pane(html)),
    ):
        for snippet in _bare_cyrillic_in_section(fragment):
            all_bad.append((name, snippet))
    assert not all_bad, f"bare Cyrillic in settings markup: {all_bad[:12]}"
