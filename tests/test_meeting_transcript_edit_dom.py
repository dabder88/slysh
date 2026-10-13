"""Meeting screen: editable transcript textarea (parity with dictaphone)."""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"
_MEETING_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "meeting.js"


def _meeting_section(html: str) -> str:
    m = re.search(
        r'<section id="view-meeting"[^>]*>.*?</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert m, "view-meeting section not found"
    return m.group(0)


def test_meeting_transcript_is_textarea_with_footer():
    html = _INDEX.read_text(encoding="utf-8")
    section = _meeting_section(html)
    assert re.search(
        r'<textarea[^>]*id="meeting-transcript"[^>]*class="[^"]*live-transcript-field',
        section,
        re.IGNORECASE,
    )
    assert 'id="meeting-counter-stats"' in section
    assert 'data-i18n="live.autosaveNote"' in section


def test_meeting_js_transcript_edit_flow():
    text = _MEETING_JS.read_text(encoding="utf-8")
    assert "meetingEditDirty" in text
    assert "scheduleMeetingTranscriptSave" in text
    assert "/segments" in text
    assert "syncMeetingTranscriptFromSegments" in text
    sync_start = text.index("function syncMeetingTranscriptFromSegments")
    sync_chunk = text[sync_start : sync_start + 500]
    assert "meetingEditDirty" in sync_chunk


def test_meeting_job_patch_segments_transcript(tmp_path):
    from fastapi.testclient import TestClient

    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind, JobStatus, Segment

    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.MEETING, str(tmp_path / "meet.wav"))
    db.set_status(job_id, JobStatus.COMPLETED)
    db.replace_segments(job_id, [Segment(0, 1000, "было")])
    client = TestClient(create_ui_app(db=db, engine=None))
    r = client.patch(
        f"/api/jobs/{job_id}/segments",
        json={"transcript": "[00:00:00] стало"},
    )
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{job_id}").json()
    assert any("стало" in (seg.get("text") or "") for seg in job.get("segments") or [])
