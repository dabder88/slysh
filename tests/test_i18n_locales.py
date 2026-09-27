import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "web" / "locales"
WEB_JS = ROOT / "web" / "js"
INDEX_HTML = ROOT / "web" / "index.html"
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
I18N_VERSIONED_IMPORT = re.compile(r"""from\s+["']\./i18n\.js\?v=""")


def _flatten(obj: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _flatten(value, path)
        else:
            keys.add(path)
    return keys


def test_ru_en_locale_keys_match():
    ru = json.loads((LOCALES / "ru.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    ru_keys = _flatten(ru)
    en_keys = _flatten(en)
    assert ru_keys == en_keys, f"diff ru-en: {sorted(ru_keys - en_keys)[:20]} ... {sorted(en_keys - ru_keys)[:20]}"


def test_en_page_strings_are_english():
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    bad = [key for key, value in en.get("page", {}).items() if CYRILLIC.search(str(value))]
    assert not bad, f"en.page still has Cyrillic: {bad[:15]}"


def test_en_locale_has_no_cyrillic():
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))

    def walk(obj, prefix=""):
        bad = []
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                bad.extend(walk(value, path))
            elif CYRILLIC.search(str(value)):
                bad.append(path)
        return bad

    bad = walk(en)
    assert not bad, f"en.json Cyrillic at: {bad[:20]} (total {len(bad)})"


def test_js_i18n_imports_are_not_versioned():
    """ES modules treat ?v= as a separate module — initI18n must share one i18n instance."""
    offenders = []
    for path in WEB_JS.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        if I18N_VERSIONED_IMPORT.search(text):
            offenders.append(path.name)
    assert not offenders, f"Remove ?v= from i18n imports: {offenders}"


def test_dashboard_batch_cards_use_i18n_keys():
    html = INDEX_HTML.read_text(encoding="utf-8")
    for key in (
        "dashboard.batchPickFolderTitle",
        "dashboard.batchPickFolderHint",
        "dashboard.batchAddFilesTitle",
        "dashboard.batchAddFilesHint",
        "queue.newBatchAddFilesNow",
        "youtube.batchFiltersSummary",
    ):
        assert f'data-i18n="{key}"' in html, f"missing {key} in index.html"
