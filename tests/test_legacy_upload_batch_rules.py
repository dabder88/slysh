"""Upload batch intake must send saved rules after closing the target modal."""
from __future__ import annotations

from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "web" / "js" / "legacy.js"


def test_confirm_upload_as_batch_captures_rules_before_close_modal():
    text = _LEGACY.read_text(encoding="utf-8")
    start = text.index("async function confirmUploadAsBatch()")
    end = text.index("export async function resolveUploadTarget", start)
    chunk = text[start:end]
    assert "const uploadRules = pendingUploadRules" in chunk
    close_idx = chunk.index("closeUploadTargetModal()")
    capture_idx = chunk.index("const uploadRules = pendingUploadRules")
    assert capture_idx < close_idx
    assert "rules: uploadRules || undefined" in chunk
    assert "rules: pendingUploadRules || undefined" not in chunk
