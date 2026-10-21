import sys

import pytest

from slysh.youtube_env import (
    find_ytdlp,
    python_has_module,
    resolve_ytdlp_command_prefix,
    resolve_youtube_python,
    ytdlp_missing_message,
    youtube_python_candidates,
)


def test_youtube_python_candidates_includes_ui_executable():
    candidates = youtube_python_candidates()
    assert sys.executable in candidates


def test_python_has_module_current_interpreter():
    assert python_has_module(sys.executable, "json") is True
    assert python_has_module(sys.executable, "yt_dlp") in {True, False}


def test_resolve_ytdlp_uses_engine_when_ui_lacks_yt_dlp(monkeypatch):
    ui_py = sys.executable
    engine_py = r"C:\fake\.venv-engine\Scripts\python.exe"

    monkeypatch.setattr(
        "slysh.youtube_env.youtube_python_candidates",
        lambda: [ui_py, engine_py],
    )

    def probe(exe: str, module: str) -> bool:
        return exe == engine_py and module == "yt_dlp"

    monkeypatch.setattr("slysh.youtube_env.python_has_module", probe)
    monkeypatch.setattr("slysh.youtube_env.shutil.which", lambda _name: None)

    prefix = resolve_ytdlp_command_prefix()
    assert prefix == [engine_py, "-m", "yt_dlp"]
    assert find_ytdlp() == f"{engine_py} -m yt_dlp"
    assert resolve_youtube_python(require="yt_dlp") == engine_py


def test_ytdlp_missing_message_suggests_local_packages_when_engine_missing(monkeypatch):
    monkeypatch.setattr("slysh.runtime_setup.engine_packages_ok", lambda: False)
    message = ytdlp_missing_message()
    assert "локальные пакеты" in message.lower() or "Локально" in message


def test_ytdlp_missing_message_suggests_reinstall_when_engine_present(monkeypatch):
    monkeypatch.setattr("slysh.runtime_setup.engine_packages_ok", lambda: True)
    message = ytdlp_missing_message()
    assert "переустановите" in message.lower() or "uv sync" in message
