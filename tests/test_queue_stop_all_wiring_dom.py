"""Stop all: bulk cancel + batch fallback."""
from __future__ import annotations

from pathlib import Path

QUEUE = Path(__file__).resolve().parents[1] / "web" / "js" / "queue.js"


def test_stop_all_bulk_and_fallback():
    text = QUEUE.read_text(encoding="utf-8")
    stop_idx = text.index("async function stopAllActive")
    body = text[stop_idx : text.index("export function initQueue")]
    assert "cancelOrphansBulk" in body
    assert "/api/queue/cancel-orphans" in text
    assert "cancelActiveBatchesBulk" in body
    assert "/api/queue/cancel-batches" in text
    assert "cancelBatch(batch.id)" in text
