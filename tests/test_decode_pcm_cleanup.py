from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from slysh.decode import (
    DECODE_FAILED_MESSAGE,
    DecodeCancelledError,
    DecodeError,
    decode_pcm_16k_mono,
)


def _pcm_glob(tmp_path: Path) -> list[Path]:
    return list(tmp_path.glob("gigaam_pcm_*.f32le"))


def test_cancel_removes_temp_pcm(monkeypatch, tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    pcm_file = tmp_path / "gigaam_pcm_test.f32le"

    def fake_mkstemp(**kw):
        fd = os.open(pcm_file, os.O_CREAT | os.O_RDWR)
        return fd, str(pcm_file)

    monkeypatch.setattr("slysh.decode.tempfile.mkstemp", fake_mkstemp)

    class _Proc:
        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        @property
        def stderr(self):
            return None

    monkeypatch.setattr("slysh.decode.subprocess.Popen", lambda *a, **k: _Proc())
    pcm_file.write_bytes(b"\x00" * 16)

    with pytest.raises(DecodeCancelledError):
        decode_pcm_16k_mono(str(wav), cancelled=lambda: True)
    assert _pcm_glob(tmp_path) == []


def test_failed_ffmpeg_removes_temp_pcm(monkeypatch, tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(8000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    pcm_file = tmp_path / "gigaam_pcm_fail.f32le"
    def fake_mkstemp(**kw):
        fd = os.open(pcm_file, os.O_CREAT | os.O_RDWR)
        return fd, str(pcm_file)

    monkeypatch.setattr("slysh.decode.tempfile.mkstemp", fake_mkstemp)

    class _Proc:
        returncode = 1

        def poll(self):
            return 1

        @property
        def stderr(self):
            return None

    monkeypatch.setattr("slysh.decode.subprocess.Popen", lambda *a, **k: _Proc())
    pcm_file.write_bytes(b"\x00" * 8)

    with pytest.raises(DecodeError) as exc_info:
        decode_pcm_16k_mono(str(wav))
    assert exc_info.value.args[0] == DECODE_FAILED_MESSAGE
    assert not pcm_file.is_file()


def test_invalid_pcm_size_removes_temp_file(monkeypatch, tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(8000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    pcm_file = tmp_path / "gigaam_pcm_bad.f32le"
    def fake_mkstemp(**kw):
        fd = os.open(pcm_file, os.O_CREAT | os.O_RDWR)
        return fd, str(pcm_file)

    monkeypatch.setattr("slysh.decode.tempfile.mkstemp", fake_mkstemp)

    class _Proc:
        returncode = 0

        def poll(self):
            return 0

        @property
        def stderr(self):
            return None

    def fake_popen(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x00\x00\x00")
        return _Proc()

    monkeypatch.setattr("slysh.decode.subprocess.Popen", fake_popen)

    with pytest.raises(DecodeError):
        decode_pcm_16k_mono(str(wav))
    assert not pcm_file.is_file()
