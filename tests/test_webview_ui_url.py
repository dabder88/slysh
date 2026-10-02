from __future__ import annotations

from slysh.app import webview_ui_url
from slysh.release_version import installed_app_layout


def test_webview_ui_url_skip_boot_in_installed_layout(tmp_path, monkeypatch):
    root = tmp_path / "app"
    root.mkdir(parents=True)
    (root / "Slysh.exe").write_text("", encoding="utf-8")
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "uv.exe").write_text("", encoding="utf-8")
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    installed_app_layout.cache_clear()
    assert webview_ui_url(8765) == "http://127.0.0.1:8765/?skip_boot_splash=1"


def test_webview_ui_url_plain_in_dev_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    installed_app_layout.cache_clear()
    assert webview_ui_url(8765) == "http://127.0.0.1:8765/"
