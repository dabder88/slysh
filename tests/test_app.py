from unittest.mock import MagicMock, patch

from slysh.app import (
    SIDEBAR_EXPANDED_MIN_WIDTH,
    WINDOW_MIN_SIZE,
    window_size,
    JsApi,
    _paths_from_drop_event,
)


def test_window_opens_at_expanded_sidebar_width():
    assert SIDEBAR_EXPANDED_MIN_WIDTH >= 1100
    assert WINDOW_MIN_SIZE[0] >= 1100
    width, height = window_size()
    assert width >= SIDEBAR_EXPANDED_MIN_WIDTH
    assert height == 720


def test_js_api_does_not_expose_window_attribute():
    api = JsApi()
    assert "window" not in vars(api)
    public = [name for name in dir(api) if not name.startswith("_")]
    assert public == [
        "open_files",
        "open_logs_folder",
        "open_path",
        "open_url",
        "pick_folder",
        "save_file",
        "ui_bootstrap_token",
    ]


def test_js_api_open_files_uses_webview_dialog():
    api = JsApi()
    fake_window = MagicMock()
    fake_window.create_file_dialog.return_value = [r"D:\talk.wav"]
    api._window = fake_window
    fake_webview = MagicMock()
    fake_webview.FileDialog.OPEN = "open"
    with patch.dict("sys.modules", {"webview": fake_webview}):
        paths = api.open_files()
    assert paths == [r"D:\talk.wav"]
    fake_window.create_file_dialog.assert_called_once()


def test_drop_event_prefers_pywebview_full_path():
    event = {
        "dataTransfer": {
            "files": [
                {"name": "talk.webm", "pywebviewFullPath": r"D:\media\talk.webm"},
                {"name": "skip.webm"},
            ]
        }
    }
    assert _paths_from_drop_event(event) == [r"D:\media\talk.webm"]
