"""Сквозной сценарий: старт → стоп → экспорт → продолжить → перерасшифровать (без torch)."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import pytest

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.catalog import ModelItem
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.providers import save_openrouter


def _wait_job(
    client: TestClient,
    job_id: int,
    *,
    status: str | None = None,
    min_segments: int = 0,
    timeout: float = 10.0,
):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()
        ok_status = status is None or last.get("status") == status
        ok_segs = min_segments <= 0 or len(last.get("segments") or []) >= min_segments
        if ok_status and ok_segs:
            return last
        time.sleep(0.03)
    raise AssertionError(
        f"timeout job={job_id} want status={status} segs>={min_segments} last={last}"
    )


@pytest.fixture
def remote_model() -> ModelItem:
    return ModelItem(
        id="test-remote",
        label="Remote test",
        backend="openrouter",
        path="",
        ready=True,
        kind="remote",
    )


def test_stop_export_resume_retranscribe_flow(
    tmp_path: Path, monkeypatch, remote_model: ModelItem
) -> None:
    """HTTP: старт → отмена с 1 сегментом → экспорт → продолжить → перерасшифровать."""
    phase = {"n": 0}

    def fake_media(**kwargs):
        cancelled = kwargs.get("cancelled") or (lambda: False)
        on_segments = kwargs.get("on_segments")
        start_ms = int(kwargs.get("start_ms") or 0)
        phase["n"] += 1
        run = phase["n"]
        if start_ms > 0:
            first = Segment(start_ms, start_ms + 500, f"cont-{run}")
        else:
            first = Segment(0, 500, f"line-{run}")
        if on_segments:
            on_segments([first])
        while not cancelled():
            time.sleep(0.01)
        return [first]

    def fake_media_resume(**kwargs):
        cancelled = kwargs.get("cancelled") or (lambda: False)
        on_segments = kwargs.get("on_segments")
        on_progress = kwargs.get("on_progress")
        start_ms = int(kwargs.get("start_ms") or 0)
        assert start_ms >= 500
        if on_progress:
            on_progress(1.0)
        second = Segment(start_ms, start_ms + 500, "line-tail")
        if on_segments:
            on_segments([second])
        if cancelled():
            return [second]
        return [second]

    calls = {"mode": "first"}

    def route_media(**kwargs):
        if calls["mode"] == "first":
            return fake_media(**kwargs)
        if calls["mode"] == "resume":
            return fake_media_resume(**kwargs)
        chunks = [
            Segment(0, 400, "fresh-1"),
            Segment(400, 800, "fresh-2"),
        ]
        on_segments = kwargs.get("on_segments")
        if on_segments:
            for piece in chunks:
                on_segments([piece])
        return chunks

    save_openrouter(api_key="sk-test")
    monkeypatch.setenv("GIGAAM_ASR_ID", "openrouter:openai/whisper-1")
    monkeypatch.setattr(api_mod, "_selected_model", lambda: remote_model)
    monkeypatch.setattr(api_mod, "_selected_asr_is_remote", lambda: True)
    monkeypatch.setattr(api_mod, "transcribe_media", route_media)
    monkeypatch.setattr(api_mod, "_selected_asr_preflight_error", lambda: None)
    monkeypatch.setattr(api_mod, "job_duration_s", lambda _job: 1.0)

    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFFxxxx")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db=db, engine=None))

    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    job = _wait_job(client, job_id, min_segments=1)
    assert job["segments"][0]["text"] == "line-1"

    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    job = _wait_job(client, job_id, status=JobStatus.CANCELLED.value)
    assert len(job["segments"]) == 1

    out = tmp_path / "partial.srt"
    export = client.post(
        f"/api/jobs/{job_id}/export",
        json={"fmt": "srt", "path": str(out)},
    )
    assert export.status_code == 200
    assert "line-1" in out.read_text(encoding="utf-8")

    db.set_progress(job_id, 0.45)
    calls["mode"] = "resume"
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert float(job.get("progress") or 0) >= 0.40
    job = _wait_job(client, job_id, status=JobStatus.COMPLETED.value)
    assert float(job.get("progress") or 0) >= 1.0
    texts = [s["text"] for s in job["segments"]]
    assert "line-1" in texts
    assert "line-tail" in texts

    calls["mode"] = "retranscribe"
    assert client.post(f"/api/jobs/{job_id}/retranscribe").status_code == 200
    job = _wait_job(client, job_id, status=JobStatus.COMPLETED.value)
    texts_after = [s["text"] for s in job["segments"]]
    assert "line-1" not in texts_after
    assert "fresh-1" in texts_after
    assert "fresh-2" in texts_after


def test_api_export_after_cancel_has_partial_text(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.replace_segments(job_id, [Segment(0, 900, "partial")])
    db.set_status(job_id, JobStatus.CANCELLED)
    client = TestClient(create_ui_app(db=db, engine=None))
    out = tmp_path / "out.srt"
    r = client.post(f"/api/jobs/{job_id}/export", json={"fmt": "srt", "path": str(out)})
    assert r.status_code == 200
    assert "partial" in out.read_text(encoding="utf-8")
