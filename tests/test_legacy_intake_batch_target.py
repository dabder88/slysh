"""Static checks: orphan file intake must not use batch target on «Файлы» tab."""
from __future__ import annotations

from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "web" / "js" / "legacy.js"
_EDITOR = Path(__file__).resolve().parents[1] / "web" / "js" / "editor.js"


def test_file_batch_target_id_requires_batches_tab():
    text = _LEGACY.read_text(encoding="utf-8")
    assert "function fileBatchTargetId()" in text
    assert 'activeMainTab !== "batches"' in text


def test_add_folder_does_not_pass_file_batch_target():
    text = _LEGACY.read_text(encoding="utf-8")
    start = text.index("async function addFolder()")
    chunk = text[start : start + 400]
    assert "fileBatchTargetId" not in chunk
    assert "openFolderAddModal([folder], null)" in chunk


def test_editor_transcript_click_seeks_only_in_view_mode():
    text = _EDITOR.read_text(encoding="utf-8")
    idx = text.index('textarea?.addEventListener("click"')
    chunk = text[idx : idx + 200]
    assert 'editorMode !== "view"' in chunk
