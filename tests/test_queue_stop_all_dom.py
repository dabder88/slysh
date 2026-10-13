"""Stop-all control in queue topbar."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_INDEX = _ROOT / "web" / "index.html"
_QUEUE = _ROOT / "web" / "js" / "queue.js"


def test_stop_all_button_in_html():
    html = _INDEX.read_text(encoding="utf-8")
    assert 'id="btn-queue-stop-all"' in html


def test_stop_all_wired_in_queue_js():
    text = _QUEUE.read_text(encoding="utf-8")
    assert "async function stopAllActive" in text
    assert "btn-queue-stop-all" in text
    assert "/api/queue/cancel-orphans" in text
    assert "/api/queue/cancel-batches" in text
    stop_idx = text.index("async function stopAllActive")
    stop_body = text[stop_idx : text.index("export function initQueue")]
    assert "isBatchPaused" in stop_body
    assert "orphansNeedingCancel" in stop_body
    assert "orphansToCancel" in stop_body
    assert "function orphansNeedingCancel" in text
    assert "isJobPausedInQueue" in text
