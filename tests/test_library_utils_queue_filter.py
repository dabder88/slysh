"""isJobInQueue rules in library-utils.js (static contract)."""
from __future__ import annotations

from pathlib import Path

UTILS = Path(__file__).resolve().parents[1] / "web" / "js" / "library-utils.js"


def test_is_job_in_queue_export_and_excludes_terminal_statuses():
    text = UTILS.read_text(encoding="utf-8")
    assert "export function isJobInQueue" in text
    assert '"completed"' in text or "'completed'" in text
    assert '"cancelled"' in text or "'cancelled'" in text
    assert '"failed"' in text or "'failed'" in text
    assert '"paused"' in text or "'paused'" in text


def test_is_job_active_engine_starting_requires_running_or_queued():
    text = UTILS.read_text(encoding="utf-8")
    idx = text.index("export function isJobActive")
    chunk = text[idx : idx + 450]
    assert "engine_starting" in chunk
    assert "queued" in chunk
