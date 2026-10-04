from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from slysh.decode import DecodeCancelledError, decode_pcm_16k_mono
from slysh.transcribe import FakeAsrBackend, FilePipeline


def test_decode_cancel_stops_ffmpeg(monkeypatch, tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))

    class _Proc:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        @property
        def stderr(self):
            return None

    proc = _Proc()

    def fake_popen(cmd, **kwargs):
        return proc

    monkeypatch.setattr("slysh.decode.subprocess.Popen", fake_popen)
    flag = {"cancel": False}

    def cancelled():
        flag["cancel"] = True
        return True

    with pytest.raises(DecodeCancelledError):
        decode_pcm_16k_mono(str(wav), cancelled=cancelled)
    assert proc.terminated


def test_queue_default_decode_forwards_cancel(monkeypatch):
    from slysh.queue import _default_decode

    seen: list[object] = []

    def fake_decode(path, **kwargs):
        seen.append(kwargs.get("cancelled"))
        arr = __import__("numpy").zeros(8, dtype=__import__("numpy").float32)
        return arr, 16000

    monkeypatch.setattr("slysh.queue.decode_pcm_16k_mono", fake_decode)
    flag = {"v": False}
    _default_decode("p", cancelled=lambda: flag["v"], start_ms=0, end_ms=1000)
    assert seen and callable(seen[0])


def test_pipeline_cancel_during_decode(monkeypatch, tmp_path):
    wav = tmp_path / "f.wav"
    sf.write(wav, np.zeros(8000, dtype=np.float32), 16000)
    cancelled = {"v": False}

    def decode(path, **kwargs):
        cancelled["v"] = True
        raise DecodeCancelledError("stop")

    pipe = FilePipeline(FakeAsrBackend())
    status, segs = pipe.transcribe(
        str(wav),
        cancelled=lambda: cancelled["v"],
        decode=decode,
    )
    assert status == "cancelled"
    assert segs == []
