#!/usr/bin/env python3
"""Smoke: installed layout + check_for_updates against GitHub (no UI)."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""


def _fetch_github_release(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _load_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        release = _fetch_github_release(url)
    except urllib.error.HTTPError as exc:
        print(f"GET {url}")
        print(f"FAILED: HTTP {exc.code}")
        if exc.code == 404 and not _load_github_token():
            print(
                "Подсказка: 404 без токена часто значит приватный репозиторий. "
                "Для конечных пользователей репозиторий должен быть public; "
                "для локальной проверки задайте GITHUB_TOKEN в .env."
            )
        print(
            "Ожидание в UI: «Не удалось проверить обновления». "
            "Нужен публичный репозиторий, хотя бы один GitHub Release "
            "и корректный github_repo в version.json."
        )
        return 2
    except Exception as exc:
        print(f"GET {url}")
        print(f"FAILED: {exc}")
        return 2

    tag = str(release.get("tag_name") or "")
    latest = updates._parse_release_version(tag)
    current = release_version()
    body = str(release.get("body") or "")
    asset = updates._pick_setup_asset(release)
    asset_name = str(asset.get("name") or "")
    sha = updates._parse_expected_sha256(body, asset_name)
    print(f"release tag: {tag} -> {latest}")
    print(f"asset: {asset_name}")
    print(f"sha256 for asset: {'yes' if sha else 'no'}")

    from slysh.ui_locale import save_ui_locale

    for locale in ("ru", "en"):
        save_ui_locale(locale)
        a = updates._pick_setup_asset(release)
        name = str(a.get("name") or "")
        digest = updates._parse_expected_sha256(body, name)
        ok = bool(digest and re.fullmatch(r"[a-f0-9]{64}", digest))
        print(f"locale {locale}: asset={name} sha256_ok={ok}")

    # Same JSON fetch as UI (public repo). For private repo use token only in this smoke.
    updates._http_json = _fetch_github_release  # type: ignore[method-assign]
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
