"""Bento sections (#view-live, #view-meeting, #view-youtube) must not expose bare Cyrillic UI text."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"

CYRILLIC = re.compile(r"[\u0400-\u04FF]")
SECTION_IDS = ("view-live", "view-meeting", "view-youtube")
I18N_ATTRS = ("data-i18n", "data-i18n-placeholder", "data-i18n-title", "data-i18n-aria-label", "data-i18n-html")


def _extract_section(html: str, section_id: str) -> str:
    pattern = rf'<section id="{section_id}"[^>]*>.*?</section>'
    m = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    assert m, f"missing #{section_id} section"
    return m.group(0)


def _strip_comments(fragment: str) -> str:
    return re.sub(r"<!--.*?-->", "", fragment, flags=re.DOTALL)


class _BareCyrillicChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, str | None]] = []
        self.violations: list[str] = []
        self._skip_depth = 0

    def _has_i18n_on_stack(self) -> bool:
        for attrs in self.stack:
            if any(attrs.get(a) for a in I18N_ATTRS):
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: v for k, v in attrs}
        self.stack.append(ad)
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text or not CYRILLIC.search(text):
            return
        if self._has_i18n_on_stack():
            return
        self.violations.append(text[:120])


def _bare_cyrillic_in_section(fragment: str) -> list[str]:
    wrapped = f"<div>{_strip_comments(fragment)}</div>"
    parser = _BareCyrillicChecker()
    parser.feed(wrapped)
    parser.close()
    return parser.violations


def test_bento_sections_have_no_bare_cyrillic_text():
    html = _INDEX.read_text(encoding="utf-8")
    all_bad: list[tuple[str, str]] = []
    for section_id in SECTION_IDS:
        section = _extract_section(html, section_id)
        for snippet in _bare_cyrillic_in_section(section):
            all_bad.append((section_id, snippet))
    assert not all_bad, f"bare Cyrillic in bento markup: {all_bad[:12]}"


def test_speaker_rename_uses_rename_label_not_display_name():
    legacy = (_REPO / "web" / "js" / "legacy.js").read_text(encoding="utf-8")
    meeting = (_REPO / "web" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "speakerRenameLabel(key)" in legacy
    assert "speakerDisplayName(key, names[key])" not in legacy.split("renderSpeakerRename")[1].split("function")[0]
    assert "speakerRenameLabel(key)" in meeting
    assert "speakerDisplayName(key, names[key])" not in meeting
