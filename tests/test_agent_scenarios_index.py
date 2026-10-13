"""Manifest paths for agent test pool exist (guard against typos in manifest)."""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO / "scripts" / "agent_test_pool_manifest.ps1"


def _paths_from_manifest() -> set[str]:
    text = _MANIFEST.read_text(encoding="utf-8")
    found = set(re.findall(r'"(tests/[^"]+|scripts/smoke_[^"]+)"', text))
    found.update(re.findall(r"Path\s*=\s*\"(scripts/[^\"]+)\"", text))
    return found


def test_agent_test_pool_manifest_paths_exist():
    assert _MANIFEST.is_file(), "missing scripts/agent_test_pool_manifest.ps1"
    paths = _paths_from_manifest()
    assert paths, "no paths parsed from manifest"
    missing = [
        p
        for p in sorted(paths)
        if not (_REPO / p.split("::", 1)[0]).is_file()
    ]
    assert not missing, f"manifest references missing files: {missing}"
