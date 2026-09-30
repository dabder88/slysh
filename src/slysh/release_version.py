from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from slysh.paths import install_root

_VERSION_JSON = "version.json"
_PYPROJECT = "pyproject.toml"


def _read_pyproject_version(root: Path) -> str | None:
    path = root / _PYPROJECT
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _read_version_json(root: Path) -> dict:
    path = root / _VERSION_JSON
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def installed_app_layout() -> bool:
    root = install_root()
    return (
        (root / "Slysh.exe").is_file()
        and (root / "runtime" / "python").is_dir()
        and (root / "bin" / "uv.exe").is_file()
    )


def release_version() -> str:
    root = install_root()
    data = _read_version_json(root)
    ver = str(data.get("version") or "").strip()
    if ver:
        return ver
    from_py = _read_pyproject_version(root)
    if from_py:
        return from_py
    try:
        from importlib.metadata import version

        return version("slysh")
    except Exception:
        return "0.0.0"


def github_repo_slug() -> str:
    data = _read_version_json(install_root())
    slug = str(data.get("github_repo") or "").strip()
    if slug and "/" in slug:
        return slug
    import os

    env = os.environ.get("SLYSH_GITHUB_REPO", "").strip()
    if env and "/" in env:
        return env
    return "slysh-app/slysh"
