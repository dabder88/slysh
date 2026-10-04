from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from slysh.decode import decode_memmap_threshold_bytes, decode_pcm_16k_mono


def test_decode_memmap_threshold_default():
    assert decode_memmap_threshold_bytes() >= 32 * 1024 * 1024


def test_large_pcm_uses_memmap(monkeypatch, tmp_path):
    wav = tmp_path / "long.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    monkeypatch.setenv("SLYSH_DECODE_MEMMAP_BYTES", "64")

    class _Proc:
        returncode = 0

        def poll(self):
            return 0

        @property
        def stderr(self):
            return None

    def fake_popen(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x00" * 256)
        return _Proc()

    monkeypatch.setattr("slysh.decode.subprocess.Popen", fake_popen)
    pcm, sr = decode_pcm_16k_mono(str(wav))
    assert sr == 16000
    assert isinstance(pcm, np.memmap)
    assert pcm.size == 64
