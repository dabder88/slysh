from types import SimpleNamespace

import numpy as np
import pytest

from slysh.cuda_fallback import format_job_asr_error, is_gpu_runtime_error
from slysh.rnnt_backend import GigaAMBackend


def test_is_gpu_runtime_error_detects_cublas():
    assert is_gpu_runtime_error(RuntimeError("cuBLAS failed with status CUBLAS_STATUS_EXECUTION_FAILED"))


def test_is_gpu_runtime_error_ignores_other():
    assert not is_gpu_runtime_error(ValueError("bad file"))


def test_format_job_asr_error_adds_hint_for_cublas():
    msg = format_job_asr_error(RuntimeError("cuBLAS failed"))
    assert "Настройках" in msg
    assert "cuBLAS" in msg


def test_gigaam_retries_on_cpu_after_cublas(monkeypatch):
    calls: list[str] = []

    class FakeModel:
        def transcribe(self, path: str):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError("cuBLAS failed with status CUBLAS_STATUS_EXECUTION_FAILED")
            return SimpleNamespace(text="привет")

    def fake_load_model(self, device: str):
        return FakeModel()

    monkeypatch.setattr(GigaAMBackend, "_load_model", fake_load_model)
    backend = GigaAMBackend.__new__(GigaAMBackend)
    backend.device = "cuda"
    backend._model = FakeModel()
    pcm = np.zeros(16000, dtype=np.float32)
    segs = backend.transcribe_chunk(pcm, lambda: False)
    assert len(calls) == 2
    assert backend.device == "cpu"
    assert segs[0].text == "привет"
