import numpy as np
from slysh.db import Database
from slysh.models import JobKind, Segment
from slysh.queue import JobQueue
from slysh.transcribe import FilePipeline

class FakeBackend:
    def transcribe_chunk(self, pcm, cancelled):
        if cancelled():
            return []
        return [Segment(0, 500, "ок")]

class FailThenOk:
    def __init__(self):
        self.n = 0

    def transcribe_chunk(self, pcm, cancelled):
        self.n += 1
        if self.n == 1:
            raise RuntimeError("cuda oom")
        return [Segment(0, 400, "текст")]

def test_second_job_completes_after_fail(tmp_path):
    db = Database(tmp_path / "app.db")
    q = JobQueue(db, FilePipeline(FailThenOk()))
    q._decode = lambda path: np.zeros(16000 * 20, dtype=np.float32)
    a = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    b = db.create_job(JobKind.FILE, str(tmp_path / "b.wav"))
    db.begin_transcription(a)
    db.begin_transcription(b)
    q.run_until_idle()
    err = (db.get_job(a)["error_text"] or "").lower()
    assert db.get_job(a)["status"] == "failed"
    assert "oom" in err or "cuda" in err or "памяти" in err
    assert db.get_job(b)["status"] == "completed"
    assert db.list_segments(b)[0].text == "текст"

def test_cancel_before_run_marks_cancelled(tmp_path):
    db = Database(tmp_path / "app.db")
    q = JobQueue(db, FilePipeline(FakeBackend()))
    q._decode = lambda path: np.zeros(16000 * 20, dtype=np.float32)
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "c.wav"))
    db.begin_transcription(job_id)
    q.cancel(job_id)
    q.run_until_idle()
    assert db.get_job(job_id)["status"] == "cancelled"


class WholeFileBackend:
    def transcribe_chunk(self, pcm, cancelled):
        raise AssertionError("chunk path should not run")

    def transcribe_file(self, pcm, cancelled, on_progress=None):
        if on_progress:
            on_progress(1.0)
        return [Segment(0, 900, "целиком")]


def test_pipeline_uses_transcribe_file_when_present(tmp_path):
    db = Database(tmp_path / "app.db")
    q = JobQueue(db, FilePipeline(WholeFileBackend()))
    q._decode = lambda path: np.zeros(16000, dtype=np.float32)
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "d.wav"))
    db.begin_transcription(job_id)
    q.run_until_idle()
    assert db.get_job(job_id)["status"] == "completed"
    assert db.list_segments(job_id)[0].text == "целиком"


def test_pipeline_offsets_transcribe_file_range(tmp_path):
    seen = {}

    class Ranged:
        def transcribe_chunk(self, pcm, cancelled):
            raise AssertionError("chunk path should not run")

        def transcribe_file(self, pcm, cancelled, on_progress=None):
            seen["n"] = len(pcm)
            return [Segment(0, 500, "кусок")]

    db = Database(tmp_path / "app.db")
    q = JobQueue(db, FilePipeline(Ranged()))
    q._decode = lambda path: np.zeros(16000 * 5, dtype=np.float32)
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "e.wav"))
    db.set_job_range(job_id, 1000, 3000)
    db.begin_transcription(job_id)
    q.run_until_idle()
    assert seen["n"] == 16000 * 2
    seg = db.list_segments(job_id)[0]
    assert seg.start_ms == 1000
    assert seg.end_ms == 1500
