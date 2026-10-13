"""Queue UI wires pause for orphans and pause-all."""
from __future__ import annotations

from pathlib import Path

_QUEUE = Path(__file__).resolve().parents[1] / "web" / "js" / "queue.js"


def test_queue_pause_job_and_pause_all_active():
    text = _QUEUE.read_text(encoding="utf-8")
    assert "async function pauseJob" in text
    assert "async function pauseAllActive" in text
    assert "/api/queue/pause-orphans" in text
    assert "`/api/jobs/${jobId}/pause`" in text
    idx = text.index("function renderActiveJobCard")
    chunk = text[idx : idx + 2200]
    assert "pauseBtn" in chunk
    assert "pauseJob(job.id)" in chunk
