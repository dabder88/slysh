from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sidebar_resizer_markup():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="sidebar-resizer"' in html
    assert "sidebar-resizer" in html
    assert 'role="separator"' in html


def test_sidebar_resize_shell_wiring():
    shell = (ROOT / "web" / "js" / "shell.js").read_text(encoding="utf-8")
    assert 'SIDEBAR_WIDTH_KEY = "sidebar-user-width"' in shell
    assert "initSidebarResize" in shell
    assert "initSidebarResize();" in shell
    assert 'from "./panel-resize.js"' in shell
    assert "bindPanelResizer" in shell


def test_sidebar_resize_styles():
    css = (ROOT / "web" / "styles" / "input.css").read_text(encoding="utf-8")
    assert "--sidebar-user-width" in css
    assert ".sidebar-resizer" in css


def test_panel_resize_module_export():
    src = (ROOT / "web" / "js" / "panel-resize.js").read_text(encoding="utf-8")
    assert "export function bindPanelResizer" in src

    editor = (ROOT / "web" / "js" / "editor.js").read_text(encoding="utf-8")
    assert 'from "./panel-resize.js"' in editor
    assert "function bindPanelResizer" not in editor
