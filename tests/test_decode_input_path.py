from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from slysh.decode import _needs_media_temp_copy, decode_pcm_16k_mono


def test_needs_media_temp_copy_for_non_ascii():
    assert _needs_media_temp_copy(Path("C:/tmp/Созвон.wav")) is True
    assert _needs_media_temp_copy(Path("C:/tmp/meeting.wav")) is False


def test_decode_ascii_path_skips_source_copy(monkeypatch, tmp_path):
    wav = tmp_path / "clip.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))

    copied: list[tuple[str, str]] = []

    def track_copy(src, dst):
        copied.append((str(src), str(dst)))

    monkeypatch.setattr("slysh.decode.shutil.copyfile", track_copy)
    monkeypatch.setattr("slysh.decode._needs_media_temp_copy", lambda _p: False)

    class _Proc:
        returncode = 0

        def poll(self):
            return 0

        @property
        def stderr(self):
            return None

    def fake_popen(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x00" * (16000 * 4))
        assert Path(cmd[cmd.index("-i") + 1]).resolve() == wav.resolve()
        return _Proc()

    monkeypatch.setattr("slysh.decode.subprocess.Popen", fake_popen)
    pcm, sr = decode_pcm_16k_mono(str(wav))
    assert sr == 16000
    assert len(pcm) == 16000
    assert copied == []
