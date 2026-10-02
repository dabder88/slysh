from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.media_access import resolve_job_media_path
from slysh.models import JobKind
from slysh.source_path import reject_path_traversal


def test_reject_path_traversal_segment(tmp_path):
    with pytest.raises(ValueError):
        reject_path_traversal(str(tmp_path / ".." / "outside.txt"))


def test_resolve_job_media_rejects_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    media = tmp_path / "clip.wav"
    media.write_bytes(b"x")
    with pytest.raises(Exception) as exc:
        resolve_job_media_path("clip.wav")
    assert getattr(exc.value, "status_code", None) == 404


def test_job_media_endpoint_blocks_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    db = Database(tmp_path / "app.db")
    secret = tmp_path / "secret.txt"
    secret.write_text("leak", encoding="utf-8")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / ".." / "secret.txt"))
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/api/jobs/{job_id}/media")
    assert resp.status_code == 404


def test_job_media_serves_absolute_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    media = tmp_path / "audio.wav"
    media.write_bytes(b"RIFF")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(media))
    app = create_ui_app(db, engine=None)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/api/jobs/{job_id}/media")
    assert resp.status_code == 200
