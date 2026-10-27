#!/usr/bin/env python3
"""Create GitHub release and upload installer assets (uses GITHUB_TOKEN from .env)."""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "dabder88/slysh"

SETUP_ASSET_NAME_RU = "Slysh-Setup-ru.exe"
SETUP_ASSET_NAME_EN = "Slysh-Setup-en.exe"


def release_upload_plan(version: str, dist: Path) -> list[tuple[Path, str]]:
    """Local installer path and GitHub asset name (versioned + canonical aliases)."""
    ver = version.strip().lstrip("v")
    ru_src = dist / f"Slysh-Setup-{ver}-ru.exe"
    en_src = dist / f"Slysh-Setup-{ver}-en.exe"
    return [
        (ru_src, ru_src.name),
        (en_src, en_src.name),
        (ru_src, SETUP_ASSET_NAME_RU),
        (en_src, SETUP_ASSET_NAME_EN),
    ]


def _load_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""


def _request(
    method: str,
    url: str,
    token: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    hdr = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
        "User-Agent": "slysh-release-publish",
    }
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    ctx = None
    if certifi is not None:
        ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(req, timeout=600.0, context=ctx) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _release_body_from_notes(path: Path) -> str:
    release_body = path.read_text(encoding="utf-8")
    lines = release_body.splitlines()
    if len(lines) > 2 and lines[0].startswith("#"):
        return "\n".join(lines[2:]).strip()
    return release_body.strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create/update GitHub Release and upload Setup exe.")
    p.add_argument("--version", required=True, help="Semver X.Y.Z (no v prefix)")
    p.add_argument(
        "--notes",
        default=None,
        help="Markdown file for release body (default: release/GITHUB_RELEASE_vX.Y.Z.md)",
    )
    p.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo")
    p.add_argument("--dist", default=None, help="Directory with installers (default: dist/)")
    p.add_argument(
        "--canonical-only",
        action="store_true",
        help="Upload only Slysh-Setup-ru.exe and Slysh-Setup-en.exe (release must exist)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = _load_token()
    if not token:
        print("GITHUB_TOKEN missing", file=sys.stderr)
        return 1

    version = args.version.strip().lstrip("v")
    tag = f"v{version}"
    dist = Path(args.dist) if args.dist else ROOT / "dist"
    full_plan = release_upload_plan(version, dist)
    if args.canonical_only:
        uploads = [(path, name) for path, name in full_plan if name in (SETUP_ASSET_NAME_RU, SETUP_ASSET_NAME_EN)]
    else:
        uploads = full_plan

    required_paths = {path for path, _ in uploads}
    for path in required_paths:
        if not path.is_file():
            print(f"Missing {path}", file=sys.stderr)
            return 1

    gh_body: str | None = None
    if not args.canonical_only:
        notes_path = Path(args.notes) if args.notes else ROOT / "release" / f"GITHUB_RELEASE_v{version}.md"
        if not notes_path.is_file():
            print(f"Missing notes file: {notes_path}", file=sys.stderr)
            return 1
        gh_body = _release_body_from_notes(notes_path)

    repo = args.repo
    status, raw = _request(
        "GET",
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        token,
    )
    release_existed = status == 200
    release: dict
    if release_existed:
        release = json.loads(raw.decode("utf-8"))
        print(f"Release exists id={release['id']}")
    else:
        if args.canonical_only:
            print(f"Release {tag} not found (required for --canonical-only)", file=sys.stderr)
            return 1
        payload = json.dumps(
            {
                "tag_name": tag,
                "name": f"Slysh! {version}",
                "body": gh_body or "",
                "draft": False,
                "prerelease": False,
                "generate_release_notes": False,
            }
        ).encode("utf-8")
        status, raw = _request(
            "POST",
            f"https://api.github.com/repos/{repo}/releases",
            token,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if status not in (200, 201):
            print(f"Create release failed HTTP {status}: {raw.decode()[:500]}", file=sys.stderr)
            return 1
        release = json.loads(raw.decode("utf-8"))
        print(f"Created release id={release['id']}")

    release_id = release["id"]
    existing = {a["name"] for a in release.get("assets") or []}

    for path, name in uploads:
        if name in existing:
            print(f"Skip upload (exists): {name}")
            continue
        size = path.stat().st_size
        print(f"Uploading {name} ({size} bytes)...")
        url = (
            f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets"
            f"?name={urllib.request.quote(name)}"
        )
        data = path.read_bytes()
        up_status, up_raw = _request(
            "POST",
            url,
            token,
            data=data,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
            },
        )
        if up_status not in (200, 201):
            print(f"Upload {name} failed HTTP {up_status}: {up_raw.decode()[:500]}", file=sys.stderr)
            return 1
        print(f"Uploaded {name}")

    if gh_body and release.get("body") != gh_body:
        payload = json.dumps({"body": gh_body}).encode("utf-8")
        st, _ = _request(
            "PATCH",
            f"https://api.github.com/repos/{repo}/releases/{release_id}",
            token,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if st == 200:
            print("Updated release body")

    status, raw = _request(
        "GET",
        f"https://api.github.com/repos/{repo}/releases/latest",
        token,
    )
    if status == 200:
        latest = json.loads(raw.decode("utf-8"))
        print(f"latest tag: {latest.get('tag_name')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
