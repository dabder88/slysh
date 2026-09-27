from types import SimpleNamespace
from unittest.mock import MagicMock

from slysh.batch_runner import BatchRunnerControl, get_runner, start_batch
from slysh.db import Database
from slysh.models import BatchStatus, JobKind, JobStatus


def test_batch_runner_skips_completed(tmp_path):
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("Run", {"skip_completed": True, "speakers": False, "export": False})
    done = db.create_job(JobKind.FILE, str(tmp_path / "done.wav"), batch_id=batch_id)
    todo = db.create_job(JobKind.FILE, str(tmp_path / "todo.wav"), batch_id=batch_id)
    db.set_status(done, JobStatus.COMPLETED)
    (tmp_path / "todo.wav").write_bytes(b"x")

    app = SimpleNamespace(state=SimpleNamespace())
    get_runner(app)  # type: ignore[arg-type]
    calls: list[int] = []

    def run_engine_job(database, url, job_id, source):
        calls.append(job_id)
        database.set_status(job_id, JobStatus.COMPLETED)

    start_batch(
        app,
        db,
        batch_id,
        ensure_engine=lambda a: "http://127.0.0.1:1",
        run_engine_job=run_engine_job,
        engine_cancel=lambda url: None,
    )
    runner = get_runner(app)
    if runner.thread:
        runner.thread.join(timeout=5)

    assert calls == [todo]
    assert db.get_batch(batch_id)["status"] == BatchStatus.COMPLETED.value


def test_batch_runner_continues_on_failure(tmp_path):
    db = Database(tmp_path / "app.db")
    batch_id = db.create_batch("Run")
    bad = db.create_job(JobKind.FILE, str(tmp_path / "bad.wav"), batch_id=batch_id)
    good = db.create_job(JobKind.FILE, str(tmp_path / "good.wav"), batch_id=batch_id)
    (tmp_path / "bad.wav").write_bytes(b"x")
    (tmp_path / "good.wav").write_bytes(b"x")

    app = SimpleNamespace(state=SimpleNamespace())
    get_runner(app)  # type: ignore[arg-type]
    calls: list[int] = []

    def run_engine_job(database, url, job_id, source):
        calls.append(job_id)
        if job_id == bad:
            database.set_status(job_id, JobStatus.FAILED)
        else:
            database.set_status(job_id, JobStatus.COMPLETED)

    start_batch(
        app,
        db,
        batch_id,
        ensure_engine=lambda a: "http://127.0.0.1:1",
        run_engine_job=run_engine_job,
        engine_cancel=lambda url: None,
    )
    runner = get_runner(app)
    if runner.thread:
        runner.thread.join(timeout=5)

    assert bad in calls and good in calls
