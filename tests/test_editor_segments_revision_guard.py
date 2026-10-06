"""F3-06: segment revision stored per job in legacy.js save path."""
from __future__ import annotations

from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "web" / "js" / "legacy.js"
_EDITOR = Path(__file__).resolve().parents[1] / "web" / "js" / "editor.js"


def test_legacy_segments_revision_per_job_map():
    src = _LEGACY.read_text(encoding="utf-8")
    assert "segmentsRevisionByJob" in src
    assert "function getSegmentsRevision" in src
    assert "function setSegmentsRevision" in src
    assert "expected_revision: revisionAtStart" in src
    assert "setSegmentsRevision(saveJobId, newRevision)" in src
    save_block = src.split("async function saveSegments", 1)[1].split("function sourceStem", 1)[0]
    rev_assign = save_block.index("setSegmentsRevision(saveJobId, newRevision)")
    applies = save_block.index("saveResponseAppliesToEditor(saveJobId, draftGenAtStart)")
    assert rev_assign < applies, "revision for saved job must update before editor apply branch"


def test_editor_poll_passes_job_id_to_sync_revision():
    src = _EDITOR.read_text(encoding="utf-8")
    assert "__syncSegmentsRevision?.(jobId, job.segments_revision)" in src
