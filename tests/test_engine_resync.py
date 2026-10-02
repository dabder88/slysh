from __future__ import annotations

from pathlib import Path

import pytest

from slysh import runtime_setup
from slysh.updates import POST_UPDATE_MARKER, engine_resync_recommended, mark_app_update_pending


@pytest.fixture
def isolated_app_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path))
    runtime_setup.reset_install_state_for_tests()
    runtime_setup.invalidate_engine_packages_cache()
    yield tmp_path


def test_engine_resync_true_when_update_marker(isolated_app_home, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda: True,
    )
    mark_app_update_pending()
    assert engine_resync_recommended() is True
    assert not (isolated_app_home / POST_UPDATE_MARKER).is_file()


def test_engine_resync_false_when_lock_drift_without_marker(isolated_app_home, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda: True,
    )
    monkeypatch.setattr("slysh.updates.uv_lock_fingerprint", lambda: "aaa")
    monkeypatch.setattr("slysh.updates.stored_lock_fingerprint", lambda: "bbb")
    assert engine_resync_recommended() is False


def test_engine_resync_false_when_packages_missing(isolated_app_home, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda: False,
    )
    mark_app_update_pending()
    assert engine_resync_recommended() is False
    assert not (isolated_app_home / POST_UPDATE_MARKER).is_file()


def test_should_show_engine_setup_modal_false_when_packages_ok(isolated_app_home, monkeypatch):
    flag = isolated_app_home / runtime_setup.PROMPT_ENGINE_SETUP
    flag.write_text("1\n", encoding="utf-8")
    assert runtime_setup.should_show_engine_setup_modal(engine_packages=True) is False
    assert not flag.is_file()
