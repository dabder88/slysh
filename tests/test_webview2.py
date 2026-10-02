from slysh.app import (
    WEBVIEW2_BOOTSTRAPPER_URL,
    WEBVIEW2_DOWNLOADING,
    WEBVIEW2_DOWNLOAD_BUTTON,
    WEBVIEW2_DOWNLOAD_FAILED,
    WEBVIEW2_INSTALLER_STARTED,
    _bootstrapper_is_executable,
    _run_webview2_download,
    _show_webview2_dialog,
    _webview2_pv,
    install_webview2_bootstrapper,
    webview2_runtime_installed,
)


def test_webview2_missing_when_registry_has_no_key(monkeypatch):
    def missing(_hive: int, _path: str) -> str | None:
        return None

    monkeypatch.setattr("slysh.app._webview2_pv", missing)
    monkeypatch.setattr("slysh.app.sys.platform", "win32")
    assert webview2_runtime_installed() is False


def test_webview2_installed_when_registry_has_version(monkeypatch):
    def present(_hive: int, path: str) -> str | None:
        if path.endswith("{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"):
            return "131.0.2903.112"
        return None

    monkeypatch.setattr("slysh.app._webview2_pv", present)
    monkeypatch.setattr("slysh.app.sys.platform", "win32")
    assert webview2_runtime_installed() is True


def test_webview2_ignores_empty_version(monkeypatch):
    monkeypatch.setattr("slysh.app._webview2_pv", lambda *_args: "0.0.0.0")
    monkeypatch.setattr("slysh.app.sys.platform", "win32")
    assert webview2_runtime_installed() is False


def test_webview2_pv_reads_string(monkeypatch):
    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _Winreg:
        @staticmethod
        def OpenKey(_hive, _path):
            return _Key()

        @staticmethod
        def QueryValueEx(_key, name):
            assert name == "pv"
            return ("120.0.1.0", 1)

    monkeypatch.setattr("winreg.OpenKey", _Winreg.OpenKey)
    monkeypatch.setattr("winreg.QueryValueEx", _Winreg.QueryValueEx)
    assert _webview2_pv(0, "ignored") == "120.0.1.0"


def test_bootstrapper_url_is_microsoft_evergreen():
    assert WEBVIEW2_BOOTSTRAPPER_URL == "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def test_bootstrapper_rejects_html_page():
    assert _bootstrapper_is_executable(b"<html>download</html>") is False
    assert _bootstrapper_is_executable(b"MZ" + b"\0" * 100) is False


def test_install_writes_exe_and_starts_it(monkeypatch, tmp_path):
    payload = b"MZ" + b"\0" * (64 * 1024)
    opened: list[str] = []

    monkeypatch.setattr(
        "slysh.app._fetch_bootstrapper_bytes",
        lambda _url: payload,
    )
    monkeypatch.setattr("slysh.app._shell_open", opened.append)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    install_webview2_bootstrapper()

    dest = tmp_path / "Slysh-MicrosoftEdgeWebview2Setup.exe"
    assert dest.read_bytes() == payload
    assert opened == [str(dest)]


def test_download_failure_opens_microsoft_page(monkeypatch):
    notes: list[str] = []

    def fail(_url: str) -> bytes:
        raise OSError("offline")

    monkeypatch.setattr("slysh.app._fetch_bootstrapper_bytes", fail)
    opened: list[str] = []
    monkeypatch.setattr("slysh.app._shell_open", opened.append)

    _run_webview2_download(notes.append)

    assert notes[0] == WEBVIEW2_DOWNLOADING
    assert notes[-1] == WEBVIEW2_DOWNLOAD_FAILED
    assert opened == [WEBVIEW2_BOOTSTRAPPER_URL]


def test_dialog_download_button_starts_installer(monkeypatch):
    monkeypatch.setattr(
        "slysh.app.install_webview2_bootstrapper",
        lambda: None,
    )
    root = _show_webview2_dialog(run=False)
    try:
        assert WEBVIEW2_DOWNLOAD_BUTTON in _button_texts(root)
        assert "Установите его и запустите программу снова." not in " ".join(_label_texts(root))
        _click_button(root, WEBVIEW2_DOWNLOAD_BUTTON)
        status = _label_texts(root)
        assert WEBVIEW2_INSTALLER_STARTED in status
    finally:
        root.destroy()


def _button_texts(widget) -> list[str]:
    found: list[str] = []
    for child in widget.winfo_children():
        if child.winfo_class() in {"TButton", "Button"}:
            found.append(child.cget("text"))
        found.extend(_button_texts(child))
    return found


def _label_texts(widget) -> list[str]:
    found: list[str] = []
    for child in widget.winfo_children():
        if child.winfo_class() == "Label":
            found.append(child.cget("text"))
        found.extend(_label_texts(child))
    return found


def _click_button(widget, text: str) -> None:
    for child in widget.winfo_children():
        if child.winfo_class() in {"TButton", "Button"} and child.cget("text") == text:
            child.invoke()
            return
        _click_button(child, text)
