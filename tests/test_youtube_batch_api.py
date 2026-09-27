from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.batch_rules import normalize_rules
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.youtube_ingest import YoutubeTranscriptResult


def test_youtube_batch_resolve_lines(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    response = client.post(
        "/api/youtube/batch/resolve",
        json={
            "mode": "lines",
            "lines": "https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://youtu.be/abcdefghijk",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["videos"][0]["video_id"] == "dQw4w9WgXcQ"
    assert body["videos"][0].get("existing_job") is None


def test_youtube_status_includes_batch_api(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.get("/api/youtube/status")
    assert response.status_code == 200
    body = response.json()
    assert body.get("batch_api") is True
    assert body.get("batch_resolve_api") is True


def test_youtube_batch_create_alias(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post(
        "/api/youtube/batch/create",
        json={
            "mode": "lines",
            "lines": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "method": "apify",
            "autostart": False,
        },
    )
    assert response.status_code == 200
    batch = response.json()
    assert batch["batch_type"] == "youtube"
    assert len(batch["jobs"]) == 1


def test_youtube_batch_create_and_start(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    monkeypatch.setattr(
        "slysh.youtube_ingest.fetch_transcript",
        lambda url, method, language="ru": YoutubeTranscriptResult(
            title="Vid",
            channel="Ch",
            channel_url="",
            upload_date="2024-01-01",
            video_id="dQw4w9WgXcQ",
            url=url,
            segments=[Segment(0, 500, "text")],
        ),
    )

    response = client.post(
        "/api/youtube/batch",
        json={
            "mode": "lines",
            "lines": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "method": "apify",
            "autostart": False,
        },
    )
    assert response.status_code == 200
    batch = response.json()
    assert batch["batch_type"] == "youtube"
    assert batch["rules"]["batch_type"] == "youtube"
    assert len(batch["jobs"]) == 1
    assert batch["jobs"][0]["kind"] == JobKind.YOUTUBE.value

    start = client.post(f"/api/batches/{batch['id']}/start")
    assert start.status_code == 200

    import time

    detail = start.json()
    for _ in range(50):
        if detail["jobs"][0]["status"] == JobStatus.COMPLETED.value:
            break
        time.sleep(0.05)
        detail = client.get(f"/api/batches/{batch['id']}").json()
    assert detail["jobs"][0]["status"] == JobStatus.COMPLETED.value


def test_add_files_to_youtube_batch_rejected(tmp_path):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    batch_id = db.create_batch("YT", normalize_rules({"batch_type": "youtube"}))
    response = client.post(
        f"/api/batches/{batch_id}/items",
        json={"paths": ["C:\\fake.mp3"], "recursive": False},
    )
    assert response.status_code == 400
