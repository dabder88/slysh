from __future__ import annotations

from pathlib import Path

from slysh.offline_bootstrap import UI_REQUIREMENTS_FILENAME
from slysh.runtime_setup import ui_wheelhouse_dir, uv_sync_ui_argv


def test_uv_sync_ui_argv_without_wheelhouse(monkeypatch, tmp_path):
    root = tmp_path / "install"
    root.mkdir()
    (root / "bin").mkdir()
    monkeypatch.setattr("slysh.runtime_setup.install_root", lambda: root)
    assert ui_wheelhouse_dir() is None
    assert uv_sync_ui_argv() == ("sync",)


def test_uv_sync_ui_argv_offline_with_wheelhouse(monkeypatch, tmp_path):
    root = tmp_path / "install"
    wh = root / "wheelhouse"
    wh.mkdir(parents=True)
    (wh / "pkg-1.0-py3-none-any.whl").write_bytes(b"x")
    monkeypatch.setattr("slysh.runtime_setup.install_root", lambda: root)
    assert ui_wheelhouse_dir() == wh
    argv = uv_sync_ui_argv()
    assert argv[0] == "sync"
    assert "--offline" in argv
    assert str(wh) in argv


def test_uv_sync_ui_argv_pip_sync_with_requirements_ui(monkeypatch, tmp_path):
    root = tmp_path / "install"
    wh = root / "wheelhouse"
    wh.mkdir(parents=True)
    (wh / "pkg-1.0-py3-none-any.whl").write_bytes(b"x")
    (wh / UI_REQUIREMENTS_FILENAME).write_text("pkg==1\n", encoding="utf-8")
    monkeypatch.setattr("slysh.runtime_setup.install_root", lambda: root)
    argv = uv_sync_ui_argv()
    assert argv[0:2] == ("pip", "sync")
    assert "--no-index" in argv
