#!/usr/bin/env python3
"""Push branch and tag using GITHUB_TOKEN from .env (HTTPS)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE = "dabder88/slysh"


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Push branch and annotated tag to GitHub via token.")
    p.add_argument("--branch", default="prod-launch", help="Branch ref to push")
    p.add_argument("--tag", required=True, help="Tag name, e.g. v1.0.2")
    p.add_argument("--remote", default=DEFAULT_REMOTE, help="GitHub owner/repo")
    p.add_argument(
        "--tag-message",
        default=None,
        help="Annotated tag message (default: Slysh <version without v>)",
    )
    p.add_argument(
        "--no-force-tag",
        action="store_true",
        help="Do not pass -f to git tag",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = _load_token()
    if not token:
        print("GITHUB_TOKEN missing", file=sys.stderr)
        return 1

    tag = args.tag.strip()
    if not tag.startswith("v"):
        print("Warning: tag usually starts with v", file=sys.stderr)

    ver = tag.lstrip("v")
    tag_msg = args.tag_message or f"Slysh {ver}"
    url = f"https://x-access-token:{token}@github.com/{args.remote}.git"

    tag_argv = ["git", "tag", "-a", tag, "-m", tag_msg]
    if not args.no_force_tag:
        tag_argv.append("-f")
    subprocess.run(tag_argv, cwd=ROOT, check=True)

    for ref in (args.branch, tag):
        print(f"Pushing {ref}...")
        r = subprocess.run(
            ["git", "push", url, ref],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout, file=sys.stderr)
            return r.returncode
    print("Push OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
