"""Engine process hides console for child subprocesses on Windows."""
from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows CREATE_NO_WINDOW")
def test_install_subprocess_hide_console_patch_merges_flags(monkeypatch):
    from slysh.subprocess_win import install_subprocess_hide_console_patch

    seen: list[dict] = []

    def fake_popen(*_args, **kwargs):
        seen.append(kwargs)
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.delattr(subprocess, "_slysh_no_console_patched", raising=False)

    install_subprocess_hide_console_patch()
    subprocess.Popen(["echo"], creationflags=0)

    assert seen
    assert seen[0].get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
    assert "startupinfo" in seen[0]
