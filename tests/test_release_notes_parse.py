from slysh import updates

SAMPLE_BODY = """# Slysh! v1.0.6

## Summary

- Fix invalid import map JSON that broke the UI with a red error banner.
- YouTube reachability check uses GET generate_204 and the correct proxy opener.
- Add **youtube_proxy_active** to status.

**Website:** https://slyshai.pro/

## Assets

- `Slysh-Setup-1.0.6-ru.exe`

## SHA-256 (required for in-app update)

```
sha256: 9782c5675f0da9673266b0f8620dfb177efdd8c4b00f89a9297b43a0744b9a41  Slysh-Setup-1.0.6-ru.exe
sha256: bc3119a594f5b99a16166ba63f834f7554f6ee24720e345239041c34abac6799  Slysh-Setup-1.0.6-en.exe
```
"""


def test_extract_release_summary_from_summary_section():
    bullets = updates.extract_release_summary(SAMPLE_BODY)
    assert len(bullets) == 3
    assert "import map" in bullets[0].lower()
    assert "youtube_proxy_active" in bullets[2]
    assert "Assets" not in bullets[0]
    assert "sha256" not in " ".join(bullets).lower()


def test_parse_expected_sha256_still_works_with_summary_body():
    digest = updates._parse_expected_sha256(
        SAMPLE_BODY,
        "Slysh-Setup-1.0.6-ru.exe",
    )
    assert digest == "9782c5675f0da9673266b0f8620dfb177efdd8c4b00f89a9297b43a0744b9a41"


def test_release_notes_for_ui_date_ru():
    ui = updates.release_notes_for_ui(
        SAMPLE_BODY,
        "2026-10-28T12:00:00Z",
        "ru",
    )
    assert len(ui["bullets"]) == 3
    assert "2026" in ui["published_date"]
    assert "октября" in ui["published_date"]


def test_plain_release_notes_text():
    text = updates.plain_release_notes_text(["One", "Two"])
    assert text == "• One\n• Two"


def test_fallback_summary_without_heading():
    body = """# Slysh! v1.0.0

Legacy paragraph about fixes without Summary section.

## Assets

- file.exe
"""
    bullets = updates.extract_release_summary(body)
    assert len(bullets) == 1
    assert "Legacy paragraph" in bullets[0]
