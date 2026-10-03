import json

from slysh.compute import settings_path
from slysh.ui_prefs import load_skip_exit_confirm, save_skip_exit_confirm


def test_skip_exit_confirm_default_false(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert load_skip_exit_confirm() is False


def test_skip_exit_confirm_save_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    save_skip_exit_confirm(True)
    assert load_skip_exit_confirm() is True
    data = json.loads(settings_path().read_text(encoding="utf-8"))
    assert data["ui"]["skip_exit_confirm"] is True
    save_skip_exit_confirm(False)
    assert load_skip_exit_confirm() is False
