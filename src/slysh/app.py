from __future__ import annotations

import json
import logging
import sys

# Expanded sidebar is 256px; 1100px leaves room after window chrome.
SIDEBAR_EXPANDED_MIN_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 720
WINDOW_MIN_SIZE = (1100, 480)


def window_size() -> tuple[int, int]:
    return SIDEBAR_EXPANDED_MIN_WIDTH, DEFAULT_WINDOW_HEIGHT


class JsApi:
    def __init__(self) -> None:
        self._window = None

    def _active_window(self):
        import webview

        return self._window or (webview.windows[0] if webview.windows else None)

    def open_files(self):
        import webview

        window = self._active_window()
        if window is None:
            return []
        return (
            window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=(
                    "Аудио и видео (*.wav;*.mp3;*.m4a;*.flac;*.ogg;*.opus;*.webm;*.mp4;*.mkv;*.avi)",
                    "Все файлы (*.*)",
                ),
            )
            or []
        )

    def save_file(self, directory: str = "", filename: str = "", fmt: str = "srt"):
        import webview

        window = self._active_window()
        if window is None:
            return None
        fmt = (fmt or "srt").lower()
        labels = {
            "md": "Markdown (*.md)",
            "srt": "Субтитры SRT (*.srt)",
            "vtt": "Субтитры VTT (*.vtt)",
            "txt": "Текст TXT (*.txt)",
        }
        result = window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=directory or "",
            save_filename=filename or f"transcript.{fmt}",
            file_types=(labels.get(fmt, "Все файлы (*.*)"), "Все файлы (*.*)"),
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def pick_folder(self, directory: str = ""):
        import webview

        window = self._active_window()
        if window is None:
            return None
        result = window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=directory or "",
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def open_path(self, path: str, reveal: bool = False):
        from slysh.open_paths import open_file, reveal_in_folder

        flag = reveal is True or str(reveal).lower() in {"1", "true", "yes"}
        try:
            if flag:
                reveal_in_folder(path)
            else:
                open_file(path)
        except FileNotFoundError as exc:
            raise FileNotFoundError("Файл не найден.") from exc
        except OSError as exc:
            raise OSError(str(exc)) from exc
        return True

    def open_logs_folder(self):
        from slysh.open_paths import reveal_in_folder
        from slysh.paths import logs_dir

        reveal_in_folder(str(logs_dir()))
        return True

    def open_url(self, url: str):
        import webbrowser

        text = str(url or "").strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("Недопустимый URL")
        webbrowser.open(text)
        return True


def _paths_from_drop_event(event) -> list[str]:
    if not isinstance(event, dict):
        return []
    files = (event.get("dataTransfer") or {}).get("files") or []
    paths: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("pywebviewFullPath") or item.get("path")
        if path:
            paths.append(str(path))
    return paths


def _bind_native_drop(window) -> None:
    from webview.dom import DOMEventHandler

    def on_drop(event) -> None:
        paths = _paths_from_drop_event(event)
        if not paths:
            return
        payload = json.dumps(paths, ensure_ascii=False)
        try:
            window.evaluate_js(f"enqueueDropped({payload})")
        except Exception:
            logging.exception("drop enqueue failed")

    try:
        window.dom.document.on("drop", DOMEventHandler(on_drop, prevent_default=True))
    except Exception:
        logging.exception("could not bind native file drop")


_WEBVIEW2_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_WEBVIEW2_KEY_PATHS = (
    rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT_ID}",
    rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT_ID}",
)
# Официальный Evergreen Bootstrapper (Microsoft Learn, WebView2 distribution).
WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_DIALOG_TITLE = "Нужен Microsoft Edge WebView2 Runtime"
WEBVIEW2_DIALOG_BODY = (
    "Без него окно Slysh не откроется. "
    "Кнопка ниже скачает официальный установщик Microsoft и запустит его. "
    "Когда установка закончится, откройте Slysh снова."
)
WEBVIEW2_DOWNLOAD_BUTTON = "Скачать и установить"
WEBVIEW2_CLOSE_BUTTON = "Закрыть"
WEBVIEW2_DOWNLOADING = "Скачиваю установщик Microsoft…"
WEBVIEW2_INSTALLER_STARTED = (
    "Установщик запущен. Когда он закончит, откройте Slysh снова."
)
WEBVIEW2_DOWNLOAD_FAILED = (
    "Не удалось скачать файл. Страница Microsoft открыта в браузере. "
    "Сохраните установщик, запустите его и снова откройте Slysh."
)
WEBVIEW2_MISSING_MESSAGE = WEBVIEW2_DIALOG_TITLE


def _webview2_pv(hive: int, path: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(hive, path) as key:
            version, _ = winreg.QueryValueEx(key, "pv")
    except OSError:
        return None
    text = str(version or "").strip()
    return text or None


def webview2_runtime_installed() -> bool:
    if sys.platform != "win32":
        return True
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in _WEBVIEW2_KEY_PATHS:
            version = _webview2_pv(hive, path)
            if version and version != "0.0.0.0":
                return True
    return False


def _bootstrapper_is_executable(data: bytes) -> bool:
    return len(data) >= 64 * 1024 and data.startswith(b"MZ")


def _fetch_bootstrapper_bytes(url: str) -> bytes:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "Slysh"})
    chunks: list[bytes] = []
    total = 0
    limit = 30 * 1024 * 1024
    with urllib.request.urlopen(request, timeout=120) as response:
        while True:
            block = response.read(64 * 1024)
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ValueError("webview2 bootstrapper is too large")
            chunks.append(block)
    return b"".join(chunks)


def _shell_open(target: str) -> None:
    import ctypes

    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    result = shell32.ShellExecuteW(None, "open", target, None, None, 1)
    code = 0 if result is None else int(result)
    if code <= 32:
        raise OSError(code)


def install_webview2_bootstrapper() -> None:
    """Download the official Microsoft bootstrapper and start it."""
    from pathlib import Path
    import tempfile

    data = _fetch_bootstrapper_bytes(WEBVIEW2_BOOTSTRAPPER_URL)
    if not _bootstrapper_is_executable(data):
        raise ValueError("webview2 bootstrapper is not an executable")
    dest = Path(tempfile.gettempdir()) / "Slysh-MicrosoftEdgeWebview2Setup.exe"
    dest.write_bytes(data)
    _shell_open(str(dest))


def _run_webview2_download(set_status) -> None:
    set_status(WEBVIEW2_DOWNLOADING)
    try:
        install_webview2_bootstrapper()
    except Exception:
        logging.exception("webview2 bootstrapper failed")
        try:
            _shell_open(WEBVIEW2_BOOTSTRAPPER_URL)
        except Exception:
            logging.exception("webview2 browser open failed")
        set_status(WEBVIEW2_DOWNLOAD_FAILED)
        return
    set_status(WEBVIEW2_INSTALLER_STARTED)


def _tell_webview2_missing_messagebox() -> None:
    import ctypes

    text = (
        f"{WEBVIEW2_DIALOG_TITLE}\n\n{WEBVIEW2_DIALOG_BODY}\n\n"
        "Нажмите «Да», чтобы скачать и запустить установщик."
    )
    answer = ctypes.windll.user32.MessageBoxW(0, text, "Slysh", 0x44)
    if answer != 6:
        return
    messages: list[str] = []
    _run_webview2_download(messages.append)
    if messages:
        ctypes.windll.user32.MessageBoxW(0, messages[-1], "Slysh", 0x40)


def _make_process_dpi_aware() -> None:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


def _show_webview2_dialog(*, run: bool = True):
    import tkinter as tk
    from tkinter import ttk

    _make_process_dpi_aware()
    root = tk.Tk()
    if not run:
        root.withdraw()
    root.title("Slysh")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(padx=24, pady=20)

    style = ttk.Style()
    style.configure("Slysh.TButton", font=("Segoe UI", 11), padding=(14, 8))

    tk.Label(
        root,
        text=WEBVIEW2_DIALOG_TITLE,
        font=("Segoe UI", 14, "bold"),
        wraplength=440,
        justify="left",
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        root,
        text=WEBVIEW2_DIALOG_BODY,
        font=("Segoe UI", 11),
        wraplength=440,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(12, 8))
    status = tk.Label(
        root,
        text="",
        font=("Segoe UI", 11),
        wraplength=440,
        justify="left",
        anchor="w",
    )
    status.pack(fill="x", pady=(8, 0))

    buttons = tk.Frame(root)
    buttons.pack(fill="x", pady=(18, 0))
    busy = {"on": False}

    def set_status(text: str) -> None:
        status.configure(text=text)
        root.update_idletasks()
        width = max(root.winfo_reqwidth(), 480)
        height = root.winfo_reqheight()
        root.geometry(f"{width}x{height}")
        root.update()

    def on_close() -> None:
        if busy["on"]:
            return
        root.destroy()

    def on_download() -> None:
        if busy["on"]:
            return
        busy["on"] = True
        download_btn.state(["disabled"])
        close_btn.state(["disabled"])
        try:
            _run_webview2_download(set_status)
        finally:
            busy["on"] = False
            download_btn.pack_forget()
            close_btn.state(["!disabled"])
            close_btn.focus_set()

    close_btn = ttk.Button(
        buttons,
        text=WEBVIEW2_CLOSE_BUTTON,
        style="Slysh.TButton",
        command=on_close,
    )
    download_btn = ttk.Button(
        buttons,
        text=WEBVIEW2_DOWNLOAD_BUTTON,
        style="Slysh.TButton",
        command=on_download,
    )
    close_btn.pack(side="right")
    download_btn.pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Return>", lambda _event: on_download())
    root.update_idletasks()
    width = max(root.winfo_reqwidth(), 480)
    height = root.winfo_reqheight()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    download_btn.focus_set()
    if not run:
        return root
    root.mainloop()
    return None


def _tell_webview2_missing() -> None:
    logging.error(WEBVIEW2_MISSING_MESSAGE)
    if sys.platform != "win32":
        return
    try:
        _show_webview2_dialog()
    except Exception:
        logging.exception("webview2 dialog failed")
        _tell_webview2_missing_messagebox()


def log_startup_crash(exc: BaseException) -> None:
    import traceback
    from datetime import datetime

    from slysh.paths import install_root, logs_dir

    tb = traceback.format_exc()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = f"{type(exc).__name__}: {exc}"
    try:
        log_dir = logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "startup-crash.log").write_text(
            f"[{stamp}] {summary}\n\n{tb}",
            encoding="utf-8",
        )
    except OSError:
        pass
    try:
        err_file = install_root() / "launch-last-error.txt"
        with err_file.open("a", encoding="utf-8") as fp:
            fp.write(f"[{stamp}] startup crash: {summary}\n")
            for line in tb.strip().splitlines()[-3:]:
                fp.write(f"{line}\n")
    except OSError:
        pass


def main() -> None:
    import threading
    import time

    from slysh.logging_setup import setup_logging

    setup_logging()

    from slysh.runtime_setup import apply_fresh_install_marker

    apply_fresh_install_marker()

    from slysh.ui_locale import configure_webview_browser_language, consume_install_ui_locale_seed

    consume_install_ui_locale_seed()
    configure_webview_browser_language()

    import uvicorn
    import webview

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.paths import app_icon_path, db_path

    if not webview2_runtime_installed():
        _tell_webview2_missing()
        return

    db = Database(db_path())
    recovered = db.recover_stale_state()
    if recovered:
        logging.info("recovered %s stale job/batch states after restart", recovered)

    app = create_ui_app(db, engine=None)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    api = JsApi()
    width, height = window_size()
    min_w = max(WINDOW_MIN_SIZE[0], width)
    window = webview.create_window(
        "Slysh",
        f"http://127.0.0.1:{port}/",
        js_api=api,
        width=width,
        height=height,
        min_size=(min_w, WINDOW_MIN_SIZE[1]),
    )
    api._window = window

    def on_loaded() -> None:
        _bind_native_drop(window)
        try:
            window.resize(width, height)
        except Exception:
            logging.debug("window.resize not available", exc_info=True)

    window.events.loaded += on_loaded
    icon = app_icon_path()
    start_kwargs: dict[str, str] = {}
    if icon is not None:
        start_kwargs["icon"] = str(icon.resolve())
    try:
        webview.start(**start_kwargs)
    except Exception:
        if "icon" in start_kwargs:
            logging.exception("webview.start failed with icon, retrying without icon")
            start_kwargs.pop("icon", None)
            webview.start(**start_kwargs)
        else:
            raise


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        log_startup_crash(exc)
        raise SystemExit(1) from exc
