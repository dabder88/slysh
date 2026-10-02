import time

import importlib
import types

import numpy as np
from fastapi import HTTPException
from fastapi.testclient import TestClient

from slysh import api as api_mod
from slysh.api import create_ui_app, engine_progress_fraction
from slysh.chunking import CHUNK_SAMPLES, SAMPLE_RATE
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.catalog import GIGAAM_ID, ModelItem
from slysh.speakers import SPEAKER_CANCELLED_MESSAGE, FakeSpeakersBackend


def _use_local_engine_asr(monkeypatch) -> None:
    """Не уходить в облачный _run_remote_job из-за GIGAAM_ASR_ID на машине разработчика."""
    ready_local = ModelItem(
        id=GIGAAM_ID,
        label="GigaAM",
        backend="rnnt",
        path="",
        ready=True,
        downloadable=True,
    )
    monkeypatch.setattr(api_mod, "_selected_model", lambda: ready_local)
    monkeypatch.setattr(api_mod, "engine_packages_ok", lambda python=None, runner=None: True)


def _patch_streaming_pcm(monkeypatch, chunks: int = 1) -> np.ndarray:
    pcm = np.zeros(CHUNK_SAMPLES * chunks, dtype=np.float32)
    monkeypatch.setattr(
        api_mod,
        "decode_pcm_16k_mono",
        lambda path: (pcm, SAMPLE_RATE),
    )
    return pcm


def test_stale_done_progress_is_not_applied_to_new_job():
    assert engine_progress_fraction({"progress": 1, "phase": "done"}) is None
    assert engine_progress_fraction({"progress": 1, "phase": "cancelled"}) is None
    assert engine_progress_fraction({"progress": 0.01, "phase": "idle"}) is None
    assert engine_progress_fraction({"progress": 0.4, "phase": "asr"}) == 0.4
    assert engine_progress_fraction({"progress": 0.01, "phase": "decode"}) == 0.01


def test_export_and_edit(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "talk.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "старый")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.patch(f"/api/jobs/{job_id}/segments", json={
        "segments": [{"start_ms": 0, "end_ms": 1000, "text": "новый", "speaker": None}]
    })
    assert r.status_code == 200
    out = tmp_path / "talk.srt"
    r = client.post(f"/api/jobs/{job_id}/export", json={"fmt": "srt", "path": str(out)})
    assert r.status_code == 200
    assert "новый" in out.read_text(encoding="utf-8")
    r = client.post(f"/api/jobs/{job_id}/export", json={"fmt": "docx"})
    assert r.status_code == 400


def test_delete_job_removes_history(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "talk.wav"))
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get("/api/jobs").json() == []


def test_patch_job_archive(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "talk.wav"))
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.patch(f"/api/jobs/{job_id}", json={"archived": True})
    assert r.status_code == 400
    db.set_status(job_id, JobStatus.COMPLETED)
    r = client.patch(f"/api/jobs/{job_id}", json={"archived": True})
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{job_id}").json()["archived"] == 1
    r = client.patch(f"/api/jobs/{job_id}", json={"archived": False})
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{job_id}").json()["archived"] == 0


def test_media_returns_existing_wav(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.get(f"/api/jobs/{job_id}/media")
    assert r.status_code == 200
    assert r.content == wav.read_bytes()


def test_job_stays_idle_until_start(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_mod,
        "_start_asr_job",
        lambda _app, _db, _job_id, _path: None,
    )
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": str(wav)})
    assert r.status_code == 200
    assert r.json()["status"] == "idle"
    assert r.json()["source_path"] == str(wav.resolve())
    started = client.post(f"/api/jobs/{r.json()['id']}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "queued"


def test_create_job_accepts_file_uri(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": wav.resolve().as_uri()})
    assert r.status_code == 200
    assert r.json()["source_path"] == str(wav.resolve())


def test_create_job_rejects_basename_without_full_path(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": "Созвон.webm"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Открыть" in detail
    assert "Созвон.webm" in detail
    assert db.list_jobs() == []


def test_job_streaming_progress_and_segments(tmp_path, monkeypatch):
    import threading

    _use_local_engine_asr(monkeypatch)
    _patch_streaming_pcm(monkeypatch, chunks=2)
    first_chunk_done = threading.Event()
    release_second = threading.Event()
    chunk_n = 0

    def fake_chunk(url, samples):
        nonlocal chunk_n
        chunk_n += 1
        if chunk_n == 1:
            first_chunk_done.set()
        else:
            release_second.wait(timeout=2)
        return {
            "segments": [
                {"start_ms": 0, "end_ms": 500, "text": f"часть{chunk_n}", "speaker": None}
            ]
        }

    monkeypatch.setattr(api_mod, "engine_health", lambda url: {"device": "cpu"})
    monkeypatch.setattr(api_mod, "transcribe_chunk", fake_chunk)
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    app = create_ui_app(db=db, engine="http://127.0.0.1:9")
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": str(wav)})
    job_id = r.json()["id"]
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    assert first_chunk_done.wait(timeout=2)
    mid = None
    for _ in range(40):
        mid = client.get(f"/api/jobs/{job_id}").json()
        if (
            mid["status"] == "running"
            and len(mid.get("segments") or []) == 1
            and float(mid.get("progress") or 0) >= 0.4
        ):
            break
        time.sleep(0.05)
    assert mid is not None
    assert mid["status"] == "running"
    assert len(mid["segments"]) == 1
    assert mid["segments"][0]["text"] == "часть1"
    assert float(mid["progress"]) >= 0.4
    release_second.set()
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "completed"
    assert len(job["segments"]) == 2


def test_job_runs_when_engine_url_set(tmp_path, monkeypatch):
    _use_local_engine_asr(monkeypatch)
    monkeypatch.setattr(api_mod, "engine_health", lambda url: {"device": "cpu"})
    _patch_streaming_pcm(monkeypatch, chunks=1)
    monkeypatch.setattr(
        api_mod,
        "transcribe_chunk",
        lambda url, samples: {
            "segments": [{"start_ms": 0, "end_ms": 500, "text": "привет", "speaker": None}]
        },
    )
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    app = create_ui_app(db=db, engine="http://127.0.0.1:9")
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": str(wav)})
    assert r.status_code == 200
    job_id = r.json()["id"]
    assert r.json()["status"] == "idle"
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert job is not None
    assert job["status"] == "completed"
    assert job["progress"] == 1
    assert job["segments"][0]["text"] == "привет"
    assert job.get("duration_s") is not None


def test_spawn_failure_marks_job_failed(tmp_path, monkeypatch):
    _use_local_engine_asr(monkeypatch)

    def boom(_app):
        raise HTTPException(status_code=500, detail="engine did not report PORT")

    monkeypatch.setattr(api_mod, "_spawn_engine", boom)
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    app = create_ui_app(db=db, engine=None, auto_start_engine=True)
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": str(wav)})
    assert r.status_code == 200
    job_id = r.json()["id"]
    assert r.json()["status"] == "idle"
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "failed":
            break
        time.sleep(0.05)
    assert job is not None
    assert job["status"] == "failed"
    assert "engine did not report PORT" in job["error_text"]


def test_create_job_returns_before_engine_spawn(tmp_path, monkeypatch):
    import threading

    _use_local_engine_asr(monkeypatch)
    started = threading.Event()
    release = threading.Event()

    def slow_spawn(_app):
        started.set()
        release.wait(timeout=5)
        raise HTTPException(status_code=500, detail="engine did not report PORT")

    monkeypatch.setattr(api_mod, "_spawn_engine", slow_spawn)
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    app = create_ui_app(db=db, engine=None, auto_start_engine=True)
    client = TestClient(app)
    r = client.post("/api/jobs", json={"path": str(wav)})
    assert r.status_code == 200
    job_id = r.json()["id"]
    assert r.json()["status"] == "idle"
    assert started.is_set() is False
    start = client.post(f"/api/jobs/{job_id}/start")
    assert start.status_code == 200
    assert start.json()["status"] == "queued"
    assert started.wait(timeout=2)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "queued"
    assert job["engine_starting"] is True
    release.set()


def test_patch_transcript_text(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "talk.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "старый")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.patch(
        f"/api/jobs/{job_id}/segments",
        json={"transcript": "[00:00:00] новый\n[00:00:20] Иван: пока"},
    )
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["transcript"].startswith("[00:00:00] новый")
    assert job["segments"][0]["text"] == "новый"
    assert job["segments"][1]["speaker"] == "Иван"


def _patch_msdd(monkeypatch, backend_cls):
    from slysh import engine_client

    def fake_ensure(app):
        return "http://engine.test"

    def fake_label(base_url, path, segments):
        labeled = backend_cls().label(path, segments)
        return {
            "segments": [
                {
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "text": s.text,
                    "speaker": s.speaker,
                }
                for s in labeled
            ]
        }

    monkeypatch.setattr("slysh.api._ensure_engine_url", fake_ensure)
    monkeypatch.setattr(engine_client, "label_speakers", fake_label)


def _wait_speakers(client, job_id: int) -> dict:
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if not job.get("speakers_running"):
            return job
        time.sleep(0.05)
    assert job is not None
    return job


def test_post_speakers_and_put_rename(tmp_path, monkeypatch):
    _patch_msdd(monkeypatch, FakeSpeakersBackend)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет"), Segment(1200, 2000, "алло")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/speakers")
    assert r.status_code == 200
    assert r.json()["started"] is True
    job = _wait_speakers(client, job_id)
    assert not job.get("speakers_error")
    segs = db.list_segments(job_id)
    assert [s.text for s in segs] == ["привет", "алло"]
    assert segs[0].speaker == "SPEAKER_00"
    assert job.get("has_speakers") is True
    assert job.get("speaker_count") == 1
    r = client.put(f"/api/jobs/{job_id}/speakers", json={"SPEAKER_00": "Иван"})
    assert r.status_code == 200
    assert db.list_segments(job_id)[0].speaker == "SPEAKER_00"
    assert db.list_speaker_names(job_id)["SPEAKER_00"] == "Иван"
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["segments"][0]["speaker"] == "Иван"
    assert job["segments"][0]["speaker_key"] == "SPEAKER_00"


def test_post_speakers_failure_keeps_text(tmp_path, monkeypatch):
    class Boom:
        def label(self, source_path, segments, *, cancelled=None):
            raise RuntimeError("nemo down")

    _patch_msdd(monkeypatch, Boom)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/speakers")
    assert r.status_code == 200
    job = _wait_speakers(client, job_id)
    assert "nemo down" in (job.get("speakers_error") or "")
    assert db.list_segments(job_id)[0].text == "привет"
    assert db.list_segments(job_id)[0].speaker is None


def test_cancel_speakers(tmp_path, monkeypatch):
    holder: dict = {"app": None}

    class SlowSpeakers:
        def label(self, source_path, segments, *, cancelled=None):
            from slysh.speakers import SpeakerCancelledError

            for _ in range(200):
                app = holder.get("app")
                if app is not None:
                    for event in getattr(app.state, "speaker_cancels", {}).values():
                        if event.is_set():
                            raise SpeakerCancelledError()
                time.sleep(0.01)
            return [
                Segment(s.start_ms, s.end_ms, s.text, speaker="SPEAKER_00")
                for s in segments
            ]

    _patch_msdd(monkeypatch, SlowSpeakers)
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    job_id = db.create_job(JobKind.FILE, str(wav))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    app = create_ui_app(db=db, engine=None)
    holder["app"] = app
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/speakers")
    assert r.status_code == 200
    time.sleep(0.05)
    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    job = _wait_speakers(client, job_id)
    assert job.get("speakers_error") == SPEAKER_CANCELLED_MESSAGE
    assert db.list_segments(job_id)[0].text == "привет"
    assert db.list_segments(job_id)[0].speaker is None


def test_retranscribe_rejects_basename_only_source(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, "Созвон.webm")
    db.set_status(job_id, JobStatus.FAILED)
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    r = client.post(f"/api/jobs/{job_id}/retranscribe")
    assert r.status_code == 400
    assert "Открыть" in r.json()["detail"]
    job = db.get_job(job_id)
    assert job["status"] == JobStatus.FAILED.value
    assert "Открыть" in job["error_text"]


def test_export_stores_last_export_path(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "talk.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    out = tmp_path / "folder" / "custom.srt"
    r = client.post(f"/api/jobs/{job_id}/export", json={"fmt": "srt", "path": str(out)})
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["last_export_path"] == str(out)
    assert out.is_file()


def test_open_path_missing_returns_404(tmp_path):
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    r = client.post("/api/open-path", json={"path": str(tmp_path / "нет.txt"), "reveal": True})
    assert r.status_code == 404


def test_speakers_missing_nemo_keeps_text(tmp_path, monkeypatch):
    from slysh.speakers_msdd import DIARIZATION_MISSING

    class Missing:
        def label(self, source_path, segments, *, cancelled=None):
            raise RuntimeError(DIARIZATION_MISSING)

    _patch_msdd(monkeypatch, Missing)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    client = TestClient(create_ui_app(db=db, engine=None))
    assert client.post(f"/api/jobs/{job_id}/speakers").status_code == 200
    job = _wait_speakers(client, job_id)
    assert "NeMo" in (job.get("speakers_error") or "")
    assert db.list_segments(job_id)[0].text == "привет"
    assert db.list_segments(job_id)[0].speaker is None


def test_start_persists_range_on_job(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db=db, engine=None))
    r = client.post(
        f"/api/jobs/{job_id}/start",
        json={"start_ms": 1500, "end_ms": 9000},
    )
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["range_start_ms"] == 1500
    assert job["range_end_ms"] == 9000


def test_start_rejects_inverted_range(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db=db, engine=None))
    r = client.post(
        f"/api/jobs/{job_id}/start",
        json={"start_ms": 9000, "end_ms": 1000},
    )
    assert r.status_code == 400


def test_start_without_body_keeps_range_null(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db=db, engine=None))
    r = client.post(f"/api/jobs/{job_id}/start")
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["range_start_ms"] is None
    assert job["range_end_ms"] is None
