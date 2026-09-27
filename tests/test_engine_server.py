from fastapi.testclient import TestClient
from slysh.engine_server import create_app
from slysh.models import Segment


class Fake:
    def transcribe_chunk(self, pcm, cancelled):
        return [Segment(0, 100, "привет")]


def test_health_and_transcribe_file(tmp_path, monkeypatch):
    import numpy as np
    app = create_app(backend=Fake(), decode=lambda p: np.zeros(16000 * 20, np.float32))
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    r = client.post("/transcribe_file", json={"path": str(wav)})
    assert r.status_code == 200
    body = r.json()
    assert body["segments"][0]["text"] == "привет"


def test_transcribe_file_range_offsets_segments(tmp_path):
    import numpy as np

    seen = {}

    class Timed:
        def transcribe_chunk(self, pcm, cancelled):
            seen["n"] = len(pcm)
            return [Segment(0, 100, "привет")]

    app = create_app(
        backend=Timed(),
        decode=lambda p: np.zeros(16000 * 5, np.float32),
    )
    client = TestClient(app)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    r = client.post(
        "/transcribe_file",
        json={"path": str(wav), "start_ms": 1000, "end_ms": 3000},
    )
    assert r.status_code == 200
    assert seen["n"] == 16000 * 2
    seg = r.json()["segments"][0]
    assert seg["start_ms"] == 1000
    assert seg["end_ms"] == 1100


def test_transcribe_chunk_and_cancel():
    import numpy as np

    class CheckingFake:
        def transcribe_chunk(self, pcm, cancelled):
            if cancelled():
                return []
            return [Segment(0, 50, "chunk")]

    app = create_app(
        backend=CheckingFake(),
        decode=lambda p: np.zeros(16000 * 20, np.float32),
    )
    client = TestClient(app)
    r = client.post("/transcribe_chunk", json={"samples": [0.0] * 16})
    assert r.status_code == 200
    assert r.json()["segments"][0]["text"] == "chunk"

    assert client.post("/cancel").status_code == 200
    r2 = client.post("/transcribe_chunk", json={"samples": [0.0] * 16})
    assert r2.json()["segments"] == []


def test_transcribe_file_after_cancel_still_works(tmp_path):
    import numpy as np

    app = create_app(backend=Fake(), decode=lambda p: np.zeros(16000 * 20, np.float32))
    client = TestClient(app)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    assert client.post("/cancel").status_code == 200
    r = client.post("/transcribe_file", json={"path": str(wav)})
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") != "cancelled"
    assert body["segments"][0]["text"] == "привет"


def test_transcribe_file_decode_error_returns_json():
    from slysh.decode import DecodeError

    def boom(_path):
        raise DecodeError("Файл не читается или ffmpeg не найден.")

    app = create_app(backend=Fake(), decode=boom)
    client = TestClient(app)
    r = client.post("/transcribe_file", json={"path": "C:\\нет.webm"})
    assert r.status_code == 400
    assert "файл" in r.json()["error"].lower() or "ffmpeg" in r.json()["error"].lower()


def test_progress_updates_across_chunks(tmp_path):
    import numpy as np

    seen: list[float] = []
    holder: dict = {}

    class RecordingFake:
        def transcribe_chunk(self, pcm, cancelled):
            seen.append(holder["client"].get("/progress").json()["progress"])
            return [Segment(0, 100, "ok")]

    app = create_app(
        backend=RecordingFake(),
        decode=lambda p: np.zeros(16000 * 40, np.float32),
    )
    client = TestClient(app)
    holder["client"] = client
    assert client.get("/progress").json()["progress"] == 0
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    r = client.post("/transcribe_file", json={"path": str(wav)})
    assert r.status_code == 200
    assert seen[0] < seen[-1]
    assert client.get("/progress").json()["progress"] == 1
    assert client.get("/progress").json()["phase"] == "done"


def test_engine_server_module_top_avoids_torch_and_gigaam():
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "slysh" / "engine_server.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    banned = {"torch", "gigaam", "slysh.rnnt_backend"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in {"torch", "gigaam"}
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in banned
            assert not node.module.startswith("torch")
            assert not node.module.startswith("gigaam.")
