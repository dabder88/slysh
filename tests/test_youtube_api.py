from pathlib import Path

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.paths import db_path
from slysh.models import JobKind, JobStatus, Segment
from slysh.youtube_ingest import YoutubeTranscriptResult
from slysh.youtube_cookies import YoutubeCookiesError


def test_youtube_ingest_apify(monkeypatch):
    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    monkeypatch.setattr(
        "slysh.providers.apify_api_key",
        lambda: "test-token",
    )

    def fake_fetch(url, method, language="ru"):
        assert method == "apify"
        return YoutubeTranscriptResult(
            title="Тестовое видео",
            channel="Канал",
            channel_url="https://www.youtube.com/channel/test",
            upload_date="2024-01-01",
            video_id="dQw4w9WgXcQ",
            url=url,
            segments=[Segment(0, 1000, "привет")],
            duration_s=19.0,
            chapters=({"title": "Вступление", "start_ms": 0},),
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        )

    monkeypatch.setattr("slysh.youtube_ingest.fetch_transcript", fake_fetch)

    def immediate_start(app_ref, db_ref, job_id, url, method=None, language=None):
        from slysh.api import _run_youtube_job, load_job_ingest_meta, save_job_ingest_meta

        resolved_method, resolved_language = load_job_ingest_meta(job_id, db=db_ref)
        if method:
            resolved_method = method
        if language:
            resolved_language = language
        save_job_ingest_meta(job_id, resolved_method, resolved_language, db=db_ref)
        _run_youtube_job(
            app_ref,
            db_ref,
            job_id,
            url,
            resolved_method,
            resolved_language,
        )

    monkeypatch.setattr("slysh.api._start_youtube_job", immediate_start)

    response = client.post(
        "/api/youtube/ingest",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "method": "apify",
            "language": "ru",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == JobKind.YOUTUBE.value
    assert body["source_title"] == "Тестовое видео"
    assert body["status"] == JobStatus.COMPLETED.value

    job_id = body["id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["segments"][0]["text"] == "привет"
    assert detail["youtube"]["title"] == "Тестовое видео"
    assert detail["youtube"]["channel"] == "Канал"
    assert detail["youtube"]["duration_s"] == 19.0
    assert detail["youtube"]["chapters"][0]["title"] == "Вступление"


def test_youtube_status_endpoint(tmp_path, monkeypatch):
    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    monkeypatch.setattr("slysh.providers.apify_api_key", lambda: "")
    monkeypatch.setattr("slysh.youtube_ingest.apify_api_key", lambda: "")
    monkeypatch.setattr("slysh.youtube_cookies.cookies_present", lambda: False)
    monkeypatch.setattr("slysh.youtube_ingest.cookies_present", lambda: False)
    monkeypatch.setattr("slysh.youtube_ytdlp.find_ytdlp", lambda: None)
    monkeypatch.setattr("slysh.youtube_ingest.probe_youtube_reachable", lambda **kw: True)
    monkeypatch.setattr("slysh.youtube_ingest.youtube_proxy_active", lambda: False)
    response = client.get("/api/youtube/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["apify_key_set"] is False
    assert payload["cookies_present"] is False
    assert payload["youtube_proxy_active"] is False
    assert payload["youtube_reachable"] is True


def test_youtube_cookies_import(tmp_path, monkeypatch):
    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    target = tmp_path / "youtube" / "cookies.txt"
    monkeypatch.setattr("slysh.youtube_cookies.youtube_cookies_path", lambda: target)
    monkeypatch.setattr("slysh.youtube_cookies.youtube_dir", lambda: target.parent)
    monkeypatch.setattr(
        "slysh.youtube_cookies._meta_path",
        lambda: target.parent / "cookies-meta.json",
    )

    response = client.post(
        "/api/youtube/cookies/import",
        json={"path": str(cookies)},
    )
    assert response.status_code == 200
    assert target.is_file()


def test_youtube_cookies_extract_endpoint(tmp_path, monkeypatch):
    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    target = tmp_path / "youtube" / "cookies.txt"
    monkeypatch.setattr("slysh.youtube_cookies.youtube_cookies_path", lambda: target)
    monkeypatch.setattr("slysh.youtube_cookies.youtube_dir", lambda: target.parent)
    monkeypatch.setattr(
        "slysh.youtube_cookies._meta_path",
        lambda: target.parent / "cookies-meta.json",
    )

    def fake_extract(browser, profile):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        return {"present": True, "updated_at": "2024-01-01T00:00:00+00:00", "source": "extract"}

    monkeypatch.setattr("slysh.api.extract_cookies", fake_extract)

    response = client.post(
        "/api/youtube/cookies/extract",
        json={"browser": "firefox", "profile": "user.default-release"},
    )
    assert response.status_code == 200
    assert response.json()["present"] is True


def test_youtube_cookies_extract_returns_400_on_error(tmp_path, monkeypatch):
    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)

    def fail_extract(browser, profile):
        raise YoutubeCookiesError("В профиле нет файла cookies")

    monkeypatch.setattr("slysh.api.extract_cookies", fail_extract)

    response = client.post(
        "/api/youtube/cookies/extract",
        json={"browser": "firefox", "profile": "empty.default"},
    )
    assert response.status_code == 400
    assert "cookies" in response.json()["detail"].lower()


def test_youtube_speakers_not_supported(tmp_path):
    db = Database(db_path())
    job_id = db.create_job(JobKind.YOUTUBE, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "текст")])

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post(f"/api/jobs/{job_id}/speakers")
    assert response.status_code == 400
    assert "YouTube" in response.json()["detail"]


def test_db_source_title_migration(tmp_path):
    db = Database(db_path())
    job_id = db.create_job(JobKind.YOUTUBE, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    db.set_job_source_title(job_id, "Заголовок")
    job = db.get_job(job_id)
    assert job["source_title"] == "Заголовок"


def test_youtube_status_reveals_apify_key_when_allowed(monkeypatch):
    from slysh.providers import save_apify

    db = Database(db_path())
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    save_apify(api_key="secret-apify-token")
    monkeypatch.setattr("slysh.provider_reveal.apify_api_key", lambda: "secret-apify-token")
    response = client.get("/api/youtube/status")
    assert response.status_code == 200
    apify = response.json()["apify"]
    assert apify["api_key_set"] is True
    assert apify.get("api_key") == "secret-apify-token"
