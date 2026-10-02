from __future__ import annotations

from unittest.mock import patch

from slysh.catalog import GIGAAM_ID
from slysh.model_download import _download_command


def test_download_command_uses_engine_python_for_whisper():
    with patch(
        "slysh.model_download._download_python_executable",
        return_value=r"C:\app\.venv-engine\Scripts\pythonw.exe",
    ):
        cmd = _download_command("whisper:tiny")
    assert cmd[0] == r"C:\app\.venv-engine\Scripts\pythonw.exe"
    assert cmd[1:4] == ["-m", "slysh.whisper_download", "--id"]


def test_download_command_uses_engine_python_for_gigaam():
    with patch(
        "slysh.model_download._download_python_executable",
        return_value=r"C:\app\.venv-engine\Scripts\pythonw.exe",
    ):
        cmd = _download_command(GIGAAM_ID)
    assert cmd == [
        r"C:\app\.venv-engine\Scripts\pythonw.exe",
        "-m",
        "slysh.rnnt_backend",
        "--download-only",
    ]
