"""Contract for isJobPausedInQueue in library-utils.js."""
from __future__ import annotations

from pathlib import Path

UTILS = Path(__file__).resolve().parents[1] / "web" / "js" / "library-utils.js"


def test_paused_in_queue_helpers_exported():
    text = UTILS.read_text(encoding="utf-8")
    assert "export function isJobPausedInQueue" in text
    assert "export function jobHasQueueParticipation" in text
    assert "export function isBatchPaused" in text
    assert "started_at" in text
    assert 'batch.status === "paused"' in text


def test_is_job_in_queue_includes_paused_helper():
    text = UTILS.read_text(encoding="utf-8")
    idx = text.index("export function isJobInQueue")
    chunk = text[idx : idx + 520]
    assert "isJobPausedInQueue" in chunk
