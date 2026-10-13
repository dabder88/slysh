#!/usr/bin/env python3
"""Smoke: installed layout + check_for_updates against GitHub (no UI)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    payload = ROOT / "dist" / "payload"
    programs = (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Slysh"
    )
    install = programs if programs.is_dir() else payload
    os.environ["SLYSH_INSTALL_ROOT"] = str(install)

    from slysh.release_version import (
        github_repo_slug,
        installed_app_layout,
        release_version,
    )
    from slysh import updates

    updates.installed_app_layout.cache_clear()

    print("=== install smoke ===")
    print(f"install_root: {install}")
    for rel in ("Slysh.exe", "runtime/python", "bin/uv.exe", "version.json"):
        p = install / rel.replace("/", os.sep)
        print(f"  {rel}: {p.is_file() or p.is_dir()}")
    print(f"installed_app_layout: {installed_app_layout()}")
    print(f"updates_enabled: {updates.updates_enabled()}")
    print(f"release_version: {release_version()}")
    print(f"github_repo: {github_repo_slug()}")

    if not updates.updates_enabled():
        print(
            "SKIP live check: not installed layout "
            "(install Setup or use dist/payload with Slysh.exe)"
        )
        return 0

    print("\n=== GitHub check ===")
    slug = github_repo_slug()
    url = f"https://api.github.com/repos/{slug}/releases/latest"
    try:
        release = updates._http_json(url)
    except Exception as exc:
        print(f"GET {url}")
        print(f"FAILED: {exc}")
        print(
            "Ожидание в UI: «Не удалось проверить обновления». "
            "Нужен публичный репозиторий, хотя бы один GitHub Release "
            "и корректный github_repo в version.json."
        )
        return 2

    tag = str(release.get("tag_name") or "")
    latest = updates._parse_release_version(tag)
    current = release_version()
    body = str(release.get("body") or "")
    sha = updates._parse_expected_sha256(body)
    asset = updates._pick_setup_asset(release)
    print(f"release tag: {tag} -> {latest}")
    print(f"asset: {asset.get('name')}")
    print(f"sha256 in body: {'yes' if sha else 'no'}")

    try:
        result = updates.check_for_updates()
    except ValueError as exc:
        print(f"check_for_updates FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["has_update"]:
        ui = "доступно обновление"
        if not result.get("expected_sha256"):
            ui += "; скачивание в приложении недоступно (нет sha256: в описании релиза)"
    elif result.get("newer_than_release"):
        ui = "установленная версия новее релиза на GitHub"
    else:
        ui = "актуальная версия"
    print(f"Ожидание в UI: {ui}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
