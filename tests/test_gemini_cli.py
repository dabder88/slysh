"""Wave A10: Gemini CLI subprocess contract."""
from __future__ import annotations

import json
from types import SimpleNamespace

from slysh.gemini_cli import transcribe_gemini_file


def test_gemini_cli_cmd_has_no_yolo(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    captured: list[list[str]] = []

    workdirs: list[str] = []

    def runner(cmd, **_kwargs):
        captured.append(list(cmd))
        if _kwargs.get("cwd"):
            workdirs.append(str(_kwargs["cwd"]))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"text": "ok"}), stderr="")

    transcribe_gemini_file(
        str(audio),
        1000,
        runner=runner,
        binary="gemini-mock",
    )
    assert captured
    flat = " ".join(captured[0])
    assert "yolo" not in flat.lower()
    assert "--output-format" in captured[0]
    assert workdirs
    assert "@audio.wav" in " ".join(captured[0])


def test_gemini_cli_cancelled_after_run_returns_empty(tmp_path):
    audio = tmp_path / "b.wav"
    audio.write_bytes(b"y")

    def runner(cmd, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='{"text":"x"}', stderr="")

    out = transcribe_gemini_file(
        str(audio),
        500,
        cancelled=lambda: True,
        runner=runner,
        binary="gemini-mock",
    )
    assert out == []
