"""Pause/stop all must not block on capabilities probe."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "web" / "js" / "queue.js"


def test_pause_and_stop_all_do_not_gate_on_restart_python_toast():
    text = QUEUE.read_text(encoding="utf-8")
    pause_idx = text.index("async function pauseAllActive")
    stop_idx = text.index("async function stopAllActive")
    pause_body = text[pause_idx : text.index("async function stopAllActive")]
    stop_body = text[stop_idx : text.index("export function initQueue")]
    assert 'showToast("apiErrors.restartPython")' not in pause_body
    assert 'showToast("apiErrors.restartPython")' not in stop_body
    assert "ensureQueueBulkCapabilities" not in pause_body
    assert "ensureQueueBulkCapabilities" not in stop_body
