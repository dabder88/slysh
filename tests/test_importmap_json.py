import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "web" / "index.html"


def _importmap_json(html: str) -> str:
    match = re.search(
        r'<script type="importmap">\s*(.*?)\s*</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert match, "importmap script block missing"
    return match.group(1).strip()


def test_importmap_is_valid_json():
    html = _INDEX.read_text(encoding="utf-8")
    payload = _importmap_json(html)
    data = json.loads(payload)
    assert isinstance(data.get("imports"), dict)
    assert len(data["imports"]) > 0
