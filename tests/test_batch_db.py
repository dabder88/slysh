from slysh.db import Database
from slysh.models import BatchStatus, JobKind, JobStatus


def test_batch_crud_and_reorder(tmp_path):
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("Test", {"speakers": True})
    batch = db.get_batch(batch_id)
    assert batch["name"] == "Test"
    assert batch["rules"]["speakers"] is True

    a = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"), batch_id=batch_id)
    b = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"), batch_id=batch_id)
    jobs = db.list_batch_jobs(batch_id)
    assert [j["id"] for j in jobs] == [a, b]

    db.reorder_batch_jobs(batch_id, [b, a])
    jobs = db.list_batch_jobs(batch_id)
    assert [j["id"] for j in jobs] == [b, a]

    orphan = db.create_job(JobKind.FILE, str(tmp_path / "solo.wav"))
    grouped = db.list_jobs_grouped()
    assert len(grouped["batches"]) == 1
    assert len(grouped["orphans"]) == 1

    assert db.remove_job_from_batch(a) is True
    assert db.get_job(a)["batch_id"] is None

    assert db.delete_batch(batch_id) is True
    assert db.get_batch(batch_id) is None
    assert db.get_job(b) is None
    assert db.get_job(a) is not None


def test_default_rules_normalized(tmp_path):
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("R")
    rules = db.get_batch(batch_id)["rules"]
    assert rules["export_fmt"] == "srt"
    assert rules["skip_completed"] is True
    assert rules["on_error"] == "continue"


def test_on_error_invalid_falls_back_to_continue(tmp_path):
    from slysh.batch_rules import normalize_rules

    rules = normalize_rules({"on_error": "halt"})
    assert rules["on_error"] == "continue"
    rules = normalize_rules({"on_error": "stop"})
    assert rules["on_error"] == "stop"


def test_recover_stale_state(tmp_path):
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("P")
    db.update_batch(batch_id, status=BatchStatus.RUNNING)
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"), batch_id=batch_id)
    db.set_status(job_id, JobStatus.RUNNING)
    assert db.recover_stale_state() == 2
    assert db.get_batch(batch_id)["status"] == BatchStatus.IDLE.value
    assert db.get_job(job_id)["status"] == JobStatus.IDLE.value
