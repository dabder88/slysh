import subprocess
import time

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, Segment
from slysh.providers import save_openrouter
from slysh.remote_asr import transcribe_media


def test_transcribe_media_calls_on_segments_per_chunk(monkeypatch):
    chunks = [("chunk-a.mp3", 0, 60_000), ("chunk-b.mp3", 60_000, 60_000)]
    monkeypatch.setattr(
        "slysh.remote_asr.prepare_stt_chunks",
        lambda *args, **kwargs: list(chunks),
    )
    calls: list[str] = []

    def fake_http(**kwargs):
        path = kwargs["audio_path"]
        calls.append(path)
        return [Segment(0, 400, path)]

    monkeypatch.setattr("slysh.remote_asr.transcribe_http_file", fake_http)
    seen: list[list[Segment]] = []

    segs = transcribe_media(
        backend="http",
        model_id="http:groq",
        source_path="talk.wav",
        on_segments=lambda piece: seen.append(list(piece)),
    )
    assert len(calls) == 2
    assert len(seen) == 2
    assert len(segs) == 2
    assert segs[1].start_ms == 60_000


def test_transcribe_media_cancel_returns_partial(monkeypatch):
    chunks = [("a.mp3", 0, 1000), ("b.mp3", 1000, 1000)]
    monkeypatch.setattr(
        "slysh.remote_asr.prepare_stt_chunks",
        lambda *args, **kwargs: list(chunks),
    )
    stop = {"v": False}

    def fake_http(**_kwargs):
        return [Segment(0, 100, "x")]

    monkeypatch.setattr("slysh.remote_asr.transcribe_http_file", fake_http)

    def on_piece(_piece):
        stop["v"] = True

    segs = transcribe_media(
        backend="http",
        model_id="http:groq",
        source_path="talk.wav",
        cancelled=lambda: stop["v"],
        on_segments=on_piece,
    )
    assert len(segs) == 1


def test_remote_file_job_appends_segments_before_complete(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "models"))
    (tmp_path / "models").mkdir()
    save_openrouter(api_key="sk-test")
    monkeypatch.setenv("GIGAAM_ASR_ID", "openrouter:openai/whisper-1")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    def fake_popen(*_args, **_kwargs):
        raise AssertionError("engine must not start for OpenRouter")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    observed: list[int] = []

    def fake_media(**kwargs):
        on_segments = kwargs.get("on_segments")
        if on_segments:
            on_segments([Segment(0, 500, "first")])
            observed.append(1)
            on_segments([Segment(500, 1000, "second")])
            observed.append(2)
        return [Segment(0, 500, "first"), Segment(500, 1000, "second")]

    monkeypatch.setattr("slysh.api.transcribe_media", fake_media)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db, engine=None, auto_start_engine=True))
    client.post(f"/api/jobs/{job_id}/start")
    final = None
    for _ in range(100):
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            final = payload
            break
        time.sleep(0.05)
    if final is None:
        final = client.get(f"/api/jobs/{job_id}").json()
    assert 1 in observed and 2 in observed
    assert final["status"] == "completed"
    assert len(final["segments"]) == 2
