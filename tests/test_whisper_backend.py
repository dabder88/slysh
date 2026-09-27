import sys

from slysh.whisper_backend import (
    FasterWhisperBackend,
    OpenAIWhisperBackend,
    load_backend,
)


def test_load_backend_pt_file(tmp_path, monkeypatch):
    pt = tmp_path / "medium.pt"
    pt.write_bytes(b"pt")
    loaded = {}

    class FakeWhisper:
        @staticmethod
        def load_model(path, device=None):
            loaded["path"] = path
            loaded["device"] = device
            return object()

    monkeypatch.setitem(sys.modules, "whisper", FakeWhisper)
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "1")
    backend = load_backend(str(pt))
    assert isinstance(backend, OpenAIWhisperBackend)
    assert loaded["path"] == str(pt)


def test_load_backend_faster_whisper_dir(tmp_path, monkeypatch):
    snap = tmp_path / "snap"
    snap.mkdir()
    captured = {}

    class FakeModel:
        def __init__(self, path, device=None, compute_type=None):
            captured["path"] = path
            captured["device"] = device

    class FakeFw:
        WhisperModel = FakeModel

    monkeypatch.setitem(sys.modules, "faster_whisper", FakeFw)
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "1")
    backend = load_backend(str(snap))
    assert isinstance(backend, FasterWhisperBackend)
    assert captured["path"] == str(snap)
