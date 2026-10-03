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
    assert "finish_app_exit" in public
    assert "exit_confirm_skipped" in public


def test_finish_app_exit_proceed_sets_approved_and_destroys():
    api = JsApi()
    fake_window = MagicMock()
    api._window = fake_window
    assert api.finish_app_exit(False, True) is True
    assert api._user_approved_exit is True
    fake_window.destroy.assert_called_once()


def test_finish_app_exit_cancel_does_not_destroy():
    api = JsApi()
    fake_window = MagicMock()
    api._window = fake_window
    assert api.finish_app_exit(False, False) is False
    assert api._user_approved_exit is False
    fake_window.destroy.assert_not_called()


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
