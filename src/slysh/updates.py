from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slysh.compute import _read_settings, mutate_settings
from slysh.paths import app_dir, install_root
from slysh.release_version import github_repo_slug, installed_app_layout, release_version
from slysh.subprocess_win import subprocess_no_console_kwargs
from slysh.ui_locale import UI_LOCALES, load_ui_locale

_ABOUT_URL_RU = "https://slyshai.pro/?utm_source=soft&utm_medium=ru"
_ABOUT_URL_EN = "https://slyshai.pro/en/?utm_source=soft&utm_medium=en"


def resolve_marketing_locale(ui_locale_hint: str | None = None) -> str:
    if ui_locale_hint is not None:
        token = str(ui_locale_hint).strip().lower()
        if token in UI_LOCALES:
            return token
    return load_ui_locale()


def default_about_url(ui_locale: str | None = None) -> str:
    locale = resolve_marketing_locale(ui_locale)
    if locale == "en":
        return _ABOUT_URL_EN
    return _ABOUT_URL_RU


def default_support_url(ui_locale: str | None = None) -> str:
    return f"{default_about_url(ui_locale)}#support"


def is_default_slyshai_marketing_url(url: str, kind: str) -> bool:
    trimmed = str(url or "").strip()
    if not trimmed:
        return False
    base = trimmed.split("#", 1)[0]
    if kind == "support":
        return trimmed in (
            f"{_ABOUT_URL_RU}#support",
            f"{_ABOUT_URL_EN}#support",
        )
    return base in (_ABOUT_URL_RU, _ABOUT_URL_EN)

SETUP_ASSET_NAME_RU = "Slysh-Setup-ru.exe"
SETUP_ASSET_NAME_EN = "Slysh-Setup-en.exe"
SETUP_ASSET_NAME_LEGACY = "Slysh-Setup.exe"
GITHUB_API = "https://api.github.com"
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
_SHA256_IN_BODY = re.compile(r"sha256:\s*([a-fA-F0-9]{64})", re.IGNORECASE)
_VERSION_TAG = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-+].*)?$", re.IGNORECASE)

_lock = threading.Lock()
_state: dict[str, Any] = {
    "phase": "idle",
    "error": None,
    "bytes_done": 0,
    "bytes_total": 0,
    "path": None,
    "sha256": None,
    "pending": None,
    "operation_id": None,
}


def updates_enabled() -> bool:
    return installed_app_layout()


def app_info(ui_locale_hint: str | None = None) -> dict[str, Any]:
    marketing_locale = resolve_marketing_locale(ui_locale_hint)
    settings = _read_settings()
    updates = settings.get("updates")
    last_check = None
    if isinstance(updates, dict) and updates.get("last_check_at"):
        last_check = updates.get("last_check_at")
    slug = github_repo_slug()
    about_raw = settings.get("about_url")
    about_url = ""
    if isinstance(about_raw, str):
        about_url = about_raw.strip()
    if not about_url:
        about_url = os.environ.get("SLYSH_ABOUT_URL", "").strip()
    if not about_url:
        about_url = default_about_url(marketing_locale)
    support_raw = settings.get("support_url")
    support_url = ""
    if isinstance(support_raw, str):
        support_url = support_raw.strip()
    if not support_url:
        support_url = os.environ.get("SLYSH_SUPPORT_URL", "").strip()
    if not support_url:
        support_url = default_support_url(marketing_locale)
    return {
        "version": release_version(),
        "install_kind": "installed" if installed_app_layout() else "development",
        "updates_enabled": updates_enabled(),
        "github_repo": slug,
        "releases_url": f"https://github.com/{slug}/releases/latest",
        "last_check_at": last_check,
        "about_url": about_url,
        "support_url": support_url,
    }


def _version_tuple(text: str) -> tuple[int, ...]:
    raw = str(text or "").strip().lstrip("v")
    match = _VERSION_TAG.match(raw)
    if not match:
        return (0,)
    parts = match.group(1).split(".")
    out: list[int] = []
    for part in parts:
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out)


def version_greater(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Slysh-Desktop-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_json(url: str, timeout: float = 45.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_github_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Неожиданный ответ GitHub API")
    return data


def _parse_release_version(tag: str) -> str:
    tag = str(tag or "").strip()
    match = _VERSION_TAG.match(tag)
    if not match:
        raise ValueError(f"Неподдерживаемый тег релиза: {tag}")
    return match.group(1)


def versioned_setup_asset_name(locale: str, version: str) -> str:
    seg = "en" if str(locale).strip().lower() == "en" else "ru"
    ver = str(version).strip().lstrip("v")
    return f"Slysh-Setup-{ver}-{seg}.exe"


def _preferred_setup_asset_names(release_version: str | None = None) -> list[str]:
    settings = _read_settings()
    locale = settings.get("ui_locale")
    if not isinstance(locale, str) or not locale.strip():
        locale = "ru"
    locale = locale.strip().lower()
    primary = SETUP_ASSET_NAME_EN if locale == "en" else SETUP_ASSET_NAME_RU
    names: list[str] = []
    if release_version:
        names.append(versioned_setup_asset_name(locale, release_version))
    names.append(primary)
    if primary == SETUP_ASSET_NAME_RU:
        names.append(SETUP_ASSET_NAME_LEGACY)
    if SETUP_ASSET_NAME_EN not in names:
        names.append(SETUP_ASSET_NAME_EN)
    if SETUP_ASSET_NAME_RU not in names:
        names.append(SETUP_ASSET_NAME_RU)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _pick_setup_asset(release: dict[str, Any]) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("В релизе нет файлов")
    tag = str(release.get("tag_name") or "")
    release_ver: str | None = None
    try:
        release_ver = _parse_release_version(tag)
    except ValueError:
        release_ver = None
    preferred = _preferred_setup_asset_names(release_ver)
    for name in preferred:
        for item in assets:
            if isinstance(item, dict) and item.get("name") == name:
                return item
    raise ValueError(f"В релизе нет установщика ({', '.join(preferred)})")


def _parse_expected_sha256(body: str, asset_name: str | None = None) -> str | None:
    text = body or ""
    name = str(asset_name or "").strip()
    if name:
        per_asset = re.compile(
            rf"sha256:\s*([a-fA-F0-9]{{64}})\s+{re.escape(name)}\b",
            re.IGNORECASE | re.MULTILINE,
        )
        match = per_asset.search(text)
        if match:
            return match.group(1).lower()
    match = _SHA256_IN_BODY.search(text)
    if not match:
        return None
    return match.group(1).lower()


def _save_last_check() -> None:
    stamp = datetime.now(timezone.utc).isoformat()

    def patch(data: dict) -> None:
        updates = data.get("updates")
        if not isinstance(updates, dict):
            updates = {}
        updates["last_check_at"] = stamp
        data["updates"] = updates

    mutate_settings(patch)


def check_for_updates() -> dict[str, Any]:
    if not updates_enabled():
        raise ValueError("Проверка обновлений доступна только в установленной копии")
    slug = github_repo_slug()
    current = release_version()
    url = f"{GITHUB_API}/repos/{slug}/releases/latest"
    try:
        release = _http_json(url)
    except urllib.error.HTTPError as exc:
        logging.warning("GitHub releases check failed: %s %s", exc.code, url)
        raise ValueError("Не удалось проверить обновления") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logging.warning("GitHub releases check failed", exc_info=True)
        raise ValueError("Не удалось проверить обновления") from exc

    tag = str(release.get("tag_name") or "")
    latest = _parse_release_version(tag)
    asset = _pick_setup_asset(release)
    asset_name = str(asset.get("name") or "")
    download_url = str(asset.get("browser_download_url") or "")
    if not download_url.startswith("https://"):
        raise ValueError("Не удалось проверить обновления")
    body = str(release.get("body") or "")
    pending = {
        "version": latest,
        "tag": tag,
        "download_url": download_url,
        "size": int(asset.get("size") or 0),
        "expected_sha256": _parse_expected_sha256(body, asset_name),
        "release_notes": body.strip(),
        "html_url": str(release.get("html_url") or f"https://github.com/{slug}/releases/tag/{tag}"),
    }
    with _lock:
        _state["pending"] = pending
        phase = str(_state.get("phase") or "idle")
        if phase == "downloading":
            pass
        elif phase == "ready":
            pass
        else:
            _state["phase"] = "idle"
            _state["error"] = None
            _state["path"] = None
            _state["sha256"] = None
            _state["operation_id"] = None
            _state["bytes_done"] = 0
            _state["bytes_total"] = pending["size"]
    _save_last_check()
    has_update = version_greater(latest, current)
    newer_than_installed = version_greater(current, latest)
    return {
        "current_version": current,
        "latest_version": latest,
        "has_update": has_update,
        "newer_than_release": newer_than_installed,
        "release_notes": pending["release_notes"],
        "html_url": pending["html_url"],
        "asset_size": pending["size"],
        "expected_sha256": pending["expected_sha256"],
    }


def download_status() -> dict[str, Any]:
    with _lock:
        return {
            "phase": _state["phase"],
            "error": _state["error"],
            "bytes_done": int(_state["bytes_done"] or 0),
            "bytes_total": int(_state["bytes_total"] or 0),
            "path": _state["path"],
            "pending_version": (_state.get("pending") or {}).get("version"),
        }


def _download_dir() -> Path:
    d = Path(os.environ.get("TEMP", str(app_dir()))) / "Slysh" / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_download_url(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Недопустимый URL загрузки")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError("Недопустимый URL загрузки")


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects to hosts outside the GitHub asset allowlist."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_download_url(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.headers.pop("Authorization", None)
        return redirected


def _download_request_headers() -> dict[str, str]:
    return {
        "User-Agent": "Slysh-Desktop-Updater",
        "Accept": "application/octet-stream",
    }


def _open_download(url: str, timeout: float = 120.0):
    _validate_download_url(url)
    opener = urllib.request.build_opener(_ValidatingRedirectHandler())
    req = urllib.request.Request(url, headers=_download_request_headers(), method="GET")
    return opener.open(req, timeout=timeout)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 256)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def _require_expected_sha256(pending: dict[str, Any]) -> str:
    expected = str(pending.get("expected_sha256") or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError(
            "В описании релиза нет строки sha256: … (64 hex). "
            "Скачивание и установка заблокированы."
        )
    return expected


def start_download() -> dict[str, Any]:
    if not updates_enabled():
        raise ValueError("Загрузка обновлений доступна только в установленной копии")
    operation_id: str | None = None
    with _lock:
        pending = _state.get("pending")
        if not pending:
            raise ValueError("Сначала проверьте обновления")
        _require_expected_sha256(pending)
        if _state["phase"] == "downloading":
            already = True
        elif _state["phase"] == "ready" and _state.get("path"):
            already = True
        else:
            already = False
            operation_id = uuid.uuid4().hex
            _state["operation_id"] = operation_id
            _state["phase"] = "downloading"
            _state["error"] = None
            _state["path"] = None
            _state["sha256"] = None
            _state["bytes_done"] = 0
            _state["bytes_total"] = int(pending.get("size") or 0)
    if not already and operation_id:
        threading.Thread(
            target=_run_download,
            args=(dict(pending), operation_id),
            daemon=True,
        ).start()
    return download_status()


def _run_download(pending: dict[str, Any], operation_id: str) -> None:
    url = str(pending.get("download_url") or "")
    version = str(pending.get("version") or "unknown")
    dest: Path | None = None
    try:
        _validate_download_url(url)
        dest = _download_dir() / f"Slysh-Setup-{version}-{operation_id[:8]}.exe"
        if dest.is_file():
            dest.unlink()
        hasher = hashlib.sha256()
        done = 0
        with _open_download(url, timeout=120.0) as resp:
            total = int(resp.headers.get("Content-Length") or pending.get("size") or 0)
            with dest.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    hasher.update(chunk)
                    done += len(chunk)
                    with _lock:
                        if _state.get("operation_id") != operation_id:
                            return
                        _state["bytes_done"] = done
                        if total > 0:
                            _state["bytes_total"] = total
        digest = hasher.hexdigest().lower()
        expected = _require_expected_sha256(pending)
        if digest != expected:
            dest.unlink(missing_ok=True)
            raise ValueError("Контрольная сумма установщика не совпала")
        with _lock:
            if _state.get("operation_id") != operation_id:
                dest.unlink(missing_ok=True)
                return
            _state["phase"] = "ready"
            _state["path"] = str(dest)
            _state["sha256"] = digest
            _state["error"] = None
    except Exception as exc:
        logging.exception("update download failed")
        with _lock:
            if _state.get("operation_id") != operation_id:
                if dest and dest.is_file():
                    dest.unlink(missing_ok=True)
                return
            _state["phase"] = "error"
            _state["error"] = str(exc) or "Не удалось скачать обновление"
            _state["path"] = None
            _state["sha256"] = None


def apply_update() -> dict[str, Any]:
    if not updates_enabled():
        raise ValueError("Установка обновления доступна только в установленной копии")
    with _lock:
        if _state["phase"] != "ready" or not _state.get("path"):
            raise ValueError("Сначала скачайте обновление")
        pending = _state.get("pending") or {}
        expected = _require_expected_sha256(pending)
        digest = str(_state.get("sha256") or "").lower()
        if digest != expected:
            raise ValueError("Контрольная сумма установщика не совпала")
        installer = Path(str(_state["path"]))
    if not installer.is_file():
        raise ValueError("Файл установщика не найден")
    on_disk = _sha256_file(installer)
    if on_disk != expected or (digest and on_disk != digest):
        raise ValueError("Контрольная сумма установщика не совпала")
    args = [
        str(installer),
        "/CURRENTUSER",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
    ]
    subprocess.Popen(
        args,
        cwd=str(installer.parent),
        **subprocess_no_console_kwargs(),
    )
    mark_app_update_pending()
    logging.info("Launched installer %s", installer)
    return {"ok": True, "quit": True}


POST_UPDATE_MARKER = "app-update-applied"


def mark_app_update_pending() -> None:
    path = app_dir() / POST_UPDATE_MARKER
    path.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")


def consume_app_update_marker() -> bool:
    path = app_dir() / POST_UPDATE_MARKER
    if not path.is_file():
        return False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logging.debug("could not remove app-update marker", exc_info=True)
    return True


def uv_lock_fingerprint() -> str | None:
    lock = install_root() / "uv.lock"
    if not lock.is_file():
        return None
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()
    except OSError:
        return None


def stored_lock_fingerprint() -> str | None:
    raw = _read_settings().get("runtime")
    if isinstance(raw, dict):
        fp = str(raw.get("lock_fingerprint") or "").strip()
        return fp or None
    return None


def save_lock_fingerprint() -> None:
    fp = uv_lock_fingerprint()
    if not fp:
        return
    def patch(data: dict) -> None:
        runtime = data.get("runtime")
        if not isinstance(runtime, dict):
            runtime = {}
        runtime["lock_fingerprint"] = fp
        data["runtime"] = runtime

    mutate_settings(patch)


def engine_resync_recommended() -> bool:
    from slysh.runtime_env import engine_slot_needs_resync
    from slysh.runtime_setup import engine_packages_ok

    if not engine_packages_ok():
        consume_app_update_marker()
        return False
    if engine_slot_needs_resync():
        return True
    marker_path = app_dir() / POST_UPDATE_MARKER
    had_marker = marker_path.is_file()
    if had_marker:
        consume_app_update_marker()
        return True
    save_lock_fingerprint()
    return False


def schedule_process_exit(delay_s: float = 0.35) -> None:
    def _exit() -> None:
        time.sleep(delay_s)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
