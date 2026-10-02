from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus


def test_find_existing_transcripts_file(tmp_path):
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"x")
    path_str = str(wav.resolve())
    job_id = db.create_job(JobKind.FILE, path_str)
    db.set_status(job_id, JobStatus.COMPLETED)

    matches = db.find_existing_transcripts(file_paths=[path_str])
    assert len(matches) == 1
    assert matches[0]["job_id"] == job_id
    assert matches[0]["kind"] == "file"


def test_find_existing_transcripts_ignores_idle_and_archived(tmp_path):
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"x")
    path_str = str(wav.resolve())
    idle_id = db.create_job(JobKind.FILE, path_str)
    done_id = db.create_job(JobKind.FILE, path_str)
    db.set_status(done_id, JobStatus.COMPLETED)
    db.set_job_archived(done_id, True)

    assert db.find_existing_transcripts(file_paths=[path_str]) == []
    assert idle_id != done_id


def test_find_existing_transcripts_youtube_video_id(tmp_path):
    db = Database(tmp_path / "app.db")
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    job_id = db.create_job(JobKind.YOUTUBE, url)
    db.set_status(job_id, JobStatus.COMPLETED)

    matches = db.find_existing_transcripts(youtube_video_ids=["dQw4w9WgXcQ"])
    assert len(matches) == 1
    assert matches[0]["video_id"] == "dQw4w9WgXcQ"


def test_library_check_existing_api_file(tmp_path):
    db = Database(tmp_path / "app.db")
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"x")
    path_str = str(wav.resolve())
    job_id = db.create_job(JobKind.FILE, path_str)
    db.set_status(job_id, JobStatus.COMPLETED)

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post(
        "/api/library/check-existing",
        json={"files": [path_str]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["matches"][0]["job_id"] == job_id


def test_library_check_existing_youtube_urls_dedupe(tmp_path):
    db = Database(tmp_path / "app.db")
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    job_id = db.create_job(JobKind.YOUTUBE, url)
    db.set_status(job_id, JobStatus.COMPLETED)

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post(
        "/api/library/check-existing",
        json={
            "youtube_urls": [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtu.be/dQw4w9WgXcQ",
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_youtube_batch_resolve_includes_existing_job(tmp_path):
    db = Database(tmp_path / "app.db")
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    job_id = db.create_job(JobKind.YOUTUBE, url)
    db.set_status(job_id, JobStatus.COMPLETED)
    db.set_job_source_title(job_id, "Rick")

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post(
        "/api/youtube/batch/resolve",
        json={
            "mode": "lines",
            "lines": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
    )
    assert response.status_code == 200
    video = response.json()["videos"][0]
    assert video["existing_job"]["id"] == job_id
    assert video["existing_job"]["source_title"] == "Rick"
