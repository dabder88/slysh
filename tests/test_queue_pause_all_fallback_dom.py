"""Bulk pause orphans with per-job fallback."""
from __future__ import annotations

from pathlib import Path

QUEUE = Path(__file__).resolve().parents[1] / "web" / "js" / "queue.js"


def test_pause_orphans_bulk_and_fallback():
    text = QUEUE.read_text(encoding="utf-8")
    assert "async function pauseOrphansBulk" in text
    assert "/api/queue/pause-orphans" in text
    assert "isBulkEndpointMissing" in text
    assert "pauseJob(job.id" in text
