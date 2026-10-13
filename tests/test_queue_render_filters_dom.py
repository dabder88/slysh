"""Queue screen filters orphans to queue-relevant jobs only."""
from __future__ import annotations

from pathlib import Path

QUEUE = Path(__file__).resolve().parents[1] / "web" / "js" / "queue.js"


def test_render_queue_uses_queue_orphans_filter():
    text = QUEUE.read_text(encoding="utf-8")
    render_idx = text.index("export function renderQueue")
    body = text[render_idx : render_idx + 2800]
    assert "isJobInQueue" in body
    assert "isJobPausedInQueue" in body
    assert "queueOrphans" in body
    assert "queueBatchJobs" in body
    assert "pausedOrphans" in body
