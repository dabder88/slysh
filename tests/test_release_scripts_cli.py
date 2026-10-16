"""CLI contracts for release helper scripts."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_git_push_help():
    r = _run("git_push_with_token.py", "--help")
    assert r.returncode == 0
    assert "--tag" in r.stdout
    assert "--branch" in r.stdout


def test_publish_release_help():
    r = _run("publish_release_assets.py", "--help")
    assert r.returncode == 0
    assert "--version" in r.stdout
    assert "--notes" in r.stdout


def test_audit_release_state_runs():
    r = _run("audit_release_state.py")
    assert r.returncode == 0
    assert "local_version_pyproject" in r.stdout
    assert "github_latest" in r.stdout
