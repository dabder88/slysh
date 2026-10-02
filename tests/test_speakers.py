from slysh.db import Database
from slysh.models import JobKind, JobStatus, Segment
from slysh.speakers import FakeSpeakersBackend, assign_speakers
from slysh.speakers_msdd import _map_by_overlap

def test_assign_does_not_drop_text(tmp_path):
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "привет"), Segment(1200, 2000, "алло")])
    assign_speakers(db, job_id, FakeSpeakersBackend())
    segs = db.list_segments(job_id)
    assert [s.text for s in segs] == ["привет", "алло"]
    assert segs[0].speaker == "SPEAKER_00"
    db.upsert_speaker(job_id, "SPEAKER_00", "Иван")
    db.upsert_speaker(job_id, "SPEAKER_00", "Борис")
    assert db.list_segments(job_id)[0].speaker == "SPEAKER_00"
    assert db.list_speaker_names(job_id)["SPEAKER_00"] == "Борис"

def test_backend_failure_leaves_transcript(tmp_path):
    class Boom:
        def label(self, source_path, segments):
            raise RuntimeError("nemo down")
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(tmp_path / "a.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    original = [Segment(0, 1000, "привет")]
    db.replace_segments(job_id, original)
    try:
        assign_speakers(db, job_id, Boom())
    except Exception:
        pass
    assert db.list_segments(job_id)[0].text == "привет"
    assert db.list_segments(job_id)[0].speaker is None


def test_map_by_overlap_keeps_text_and_assigns_speakers():
    segs = [Segment(0, 1000, "привет"), Segment(1200, 2000, "алло")]
    turns = [(0, 900, "SPEAKER_00"), (1100, 2100, "SPEAKER_01")]
    labeled = _map_by_overlap(segs, turns)
    assert [s.text for s in labeled] == ["привет", "алло"]
    assert labeled[0].speaker == "SPEAKER_00"
    assert labeled[1].speaker == "SPEAKER_01"
