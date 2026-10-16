#!/usr/bin/env python3
"""JSON snapshot for release audit: git, local version, GitHub latest (public API)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "dabder88/slysh"


def _read_local_version() -> str:
    py = ROOT / "pyproject.toml"
    if py.is_file():
        m = re.search(r'^version\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip()
    return ""


def _git(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def _latest_tag() -> str:
    out = _git("describe", "--tags", "--abbrev=0")
    return out if out and not out.startswith("fatal") else ""


def _github_latest(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "slysh-audit-release",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    body = str(data.get("body") or "")
    assets = [str(a.get("name") or "") for a in data.get("assets") or []]
    return {
        "tag_name": data.get("tag_name"),
        "assets": assets,
        "has_sha256_in_body": "sha256:" in body.lower(),
    }


def _installed_version() -> str | None:
    import os

    prog = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Slysh" / "version.json"
    if not prog.is_file():
        return None
    try:
        data = json.loads(prog.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return str(data.get("version") or "") or None


def main() -> int:
    repo = DEFAULT_REPO
    payload_path = ROOT / "dist" / "payload" / "version.json"
    payload_version = None
    if payload_path.is_file():
        try:
            payload_version = json.loads(payload_path.read_text(encoding="utf-8-sig")).get("version")
        except (OSError, json.JSONDecodeError):
            pass

    dirty = _git("status", "--porcelain")
    report = {
        "repo_root": str(ROOT),
        "github_repo": repo,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "local_version_pyproject": _read_local_version(),
        "payload_version_json": payload_version,
        "installed_programs_version": _installed_version(),
        "latest_git_tag": _latest_tag(),
        "commits_since_tag": _git("rev-list", f"{_latest_tag()}..HEAD", "--count")
        if _latest_tag()
        else _git("rev-list", "HEAD", "--count"),
        "git_dirty": bool(dirty),
        "git_dirty_files_count": len([ln for ln in dirty.splitlines() if ln.strip()]) if dirty else 0,
        "github_latest": _github_latest(repo),
        "dist_installers": sorted(
            p.name for p in (ROOT / "dist").glob("Slysh-Setup-*.exe") if p.is_file()
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
