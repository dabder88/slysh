from slysh.compute import compute_payload
from slysh.ui_locale import save_ui_locale


def test_compute_payload_english_explanations(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    save_ui_locale("en")
    payload = compute_payload()
    assert payload["ui_locale"] == "en"
    assert "auto" in payload["explanations"]
    assert payload["explanations"]["auto"] != compute_payload(ui_locale="ru")["explanations"]["auto"]
