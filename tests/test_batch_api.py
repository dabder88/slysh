from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment


def test_scan_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.post("/api/batches/scan", json={"paths": [str(wav)], "recursive": False})
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert str(wav.resolve()) in r.json()["paths"]


def test_create_batch_and_add_items(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db, engine=None))
    created = client.post("/api/batches", json={"name": "Pack"}).json()
    batch_id = created["id"]
    r = client.post(f"/api/batches/{batch_id}/items", json={"paths": [str(wav)]})
    assert r.status_code == 200
    jobs = client.get("/api/batches").json()[0]["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["batch_id"] == batch_id


def test_orphan_job_via_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    wav = tmp_path / "solo.wav"
    wav.write_bytes(b"x")
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    job = client.post("/api/jobs", json={"path": str(wav)}).json()
    assert job.get("batch_id") is None


def test_reorder_batch_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    a = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"), batch_id=batch_id)
    b = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"), batch_id=batch_id)
    client = TestClient(create_ui_app(db, engine=None))
    r = client.put(f"/api/batches/{batch_id}/reorder", json={"job_ids": [b, a]})
    assert r.status_code == 200
    jobs = client.get(f"/api/batches/{batch_id}").json()["jobs"]
    assert [j["id"] for j in jobs] == [b, a]


def test_export_batch_writes_all_completed(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    ready = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"), batch_id=batch_id)
    db.create_job(JobKind.FILE, str(tmp_path / "b.wav"), batch_id=batch_id)
    other = db.create_job(JobKind.FILE, str(tmp_path / "same.wav"), batch_id=batch_id)
    db.set_status(ready, JobStatus.COMPLETED)
    db.replace_segments(ready, [Segment(0, 1000, "раз")])
    db.set_status(other, JobStatus.COMPLETED)
    db.replace_segments(other, [Segment(0, 1000, "два")])
    out_dir = tmp_path / "exports"
    client = TestClient(create_ui_app(db, engine=None))
    r = client.post(
        f"/api/batches/{batch_id}/export",
        json={"fmt": "srt", "directory": str(out_dir)},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["exported"] == 2
    assert payload["skipped"] == 1
    assert (out_dir / "a.srt").is_file()
    assert (out_dir / "same.srt").is_file()
    assert not (out_dir / "b.srt").exists()
    assert "раз" in (out_dir / "a.srt").read_text(encoding="utf-8")
    job = client.get(f"/api/jobs/{ready}").json()
    assert job["last_export_path"] == str(out_dir / "a.srt")


def test_export_jobs_same_stem_gets_suffix(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    first = db.create_job(JobKind.FILE, str(tmp_path / "dir1" / "talk.wav"))
    second = db.create_job(JobKind.FILE, str(tmp_path / "dir2" / "talk.wav"))
    db.set_status(first, JobStatus.COMPLETED)
    db.set_status(second, JobStatus.COMPLETED)
    db.replace_segments(first, [Segment(0, 1000, "один")])
    db.replace_segments(second, [Segment(0, 1000, "два")])
    out_dir = tmp_path / "out"
    client = TestClient(create_ui_app(db, engine=None))
    r = client.post(
        "/api/export-jobs",
        json={"fmt": "txt", "directory": str(out_dir), "job_ids": [first, second]},
    )
    assert r.status_code == 200
    assert r.json()["exported"] == 2
    assert (out_dir / "talk.txt").read_text(encoding="utf-8").strip() == "один"
    assert (out_dir / "talk_2.txt").read_text(encoding="utf-8").strip() == "два"


def test_export_batch_empty_completed_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    db.create_job(JobKind.FILE, str(tmp_path / "a.wav"), batch_id=batch_id)
    client = TestClient(create_ui_app(db, engine=None))
    r = client.post(
        f"/api/batches/{batch_id}/export",
        json={"fmt": "srt", "directory": str(tmp_path / "out")},
    )
    assert r.status_code == 400
