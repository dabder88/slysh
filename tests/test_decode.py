# tests/test_decode.py
import shutil
import subprocess as sp
import sys

import pytest
from slysh.decode import (
    DecodeError,
    decode_pcm_16k_mono,
    find_ffmpeg,
)


class _Proc:
    returncode = 0
    stderr = b"Duration: 00:00:01.00"
    stdout = b"\x00" * (16000 * 4)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows subprocess flags")
def test_decode_ffmpeg_subprocess_hides_console(monkeypatch, tmp_path):
    import numpy as np
    import soundfile as sf

    seen: list[dict] = []

    def fake_run(cmd, **kwargs):
        seen.append(kwargs)
        return _Proc()

    monkeypatch.setattr("slysh.decode.subprocess.run", fake_run)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    decode_pcm_16k_mono(str(wav))
    assert len(seen) >= 1
    assert seen[0]["creationflags"] == sp.CREATE_NO_WINDOW
    assert seen[0]["startupinfo"] is not None


def test_missing_file_raises():
    with pytest.raises(DecodeError, match="файл|прочитать"):
        decode_pcm_16k_mono("Z:\\does-not-exist-gigaam.wav")


def test_find_ffmpeg_uses_env(tmp_path, monkeypatch):
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    assert find_ffmpeg() == str(fake)


def test_decode_uses_bundled_ffmpeg_without_path(tmp_path, monkeypatch):
    from slysh.paths import install_root

    bundled = install_root() / "bin" / "ffmpeg.exe"
    if not bundled.is_file():
        pytest.fail("bundled ffmpeg missing")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    import numpy as np
    import soundfile as sf

    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    pcm, sr = decode_pcm_16k_mono(str(wav))
    assert sr == 16000
    assert pcm.ndim == 1
    assert len(pcm) >= 16000 - 160


def test_silence_wav_roundtrip(tmp_path):
    import numpy as np
    import soundfile as sf
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    pcm, sr = decode_pcm_16k_mono(str(wav))
    assert sr == 16000
    assert pcm.ndim == 1
    assert len(pcm) >= 16000 - 160  # allow ffmpeg padding


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_cyrillic_filename_roundtrip(tmp_path):
    import numpy as np
    import soundfile as sf

    wav = tmp_path / "Созвон 11.08.26 - правки.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    pcm, sr = decode_pcm_16k_mono(str(wav))
    assert sr == 16000
    assert len(pcm) >= 16000 - 160
