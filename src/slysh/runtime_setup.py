from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from slysh.offline_bootstrap import offline_pip_sync_ready, uv_pip_sync_argv
from slysh.paths import app_dir, install_root, logs_dir, project_root
from slysh.subprocess_win import subprocess_no_console_kwargs

PROBE_IMPORTS = "import torch, gigaam"
LATER_FLAG_NAME = "setup-engine-later"
MODEL_PENDING_FLAG = "setup-pending-model-download"
PROMPT_ENGINE_SETUP = "prompt-engine-setup"
ENGINE_SETUP_LOG = "engine-setup.log"
UV_EXTRAS = ("sync", "--extra", "engine", "--extra", "diarization", "--extra", "youtube")


def ui_wheelhouse_dir() -> Path | None:
    """Bundled wheels for offline repair of the light UI venv (installer payload)."""
    wh = install_root() / "wheelhouse"
    if not wh.is_dir():
        return None
    if not any(wh.glob("*.whl")):
        return None
    return wh


def uv_sync_ui_argv() -> tuple[str, ...]:
    """Light UI venv sync (Slysh.bat :ensure_venv). Uses wheelhouse when present."""
    root = install_root()
    if offline_pip_sync_ready(root):
        return tuple(uv_pip_sync_argv(root))
    wh = ui_wheelhouse_dir()
    if wh is None:
        return ("sync",)
    return (
        "sync",
        "--no-editable",
        "--no-dev",
        "--find-links",
        str(wh),
        "--offline",
    )


def uv_sync_engine_argv() -> tuple[str, ...]:
    """CLI args for engine package install. Set SLYSH_ENGINE_INSTALL_NO_CACHE=1 for QA without uv cache."""
    parts = ["sync"]
    if os.environ.get("SLYSH_ENGINE_INSTALL_NO_CACHE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        parts.append("--no-cache")
    parts.extend(["--extra", "engine", "--extra", "diarization", "--extra", "youtube"])
    return tuple(parts)


ENGINE_PACKAGES_CACHE_TTL_S = 45.0
ENGINE_SETUP_LOG_TAIL_INSTALL = 65536
ENGINE_SETUP_STALL_SECONDS = 90.0

_DOWNLOADING_LINE = re.compile(
    r"^Downloading\s+(?P<name>[^\s(]+)(?:\s*\((?P<size>[^)]+)\))?\s*$",
    re.IGNORECASE,
)
_DOWNLOADED_LINE = re.compile(r"^Downloaded\s+(?P<name>\S+)\s*$", re.IGNORECASE)
_SIZE_TOKEN = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>GiB|MiB|KiB)",
    re.IGNORECASE,
)
_BYTE_PAIR = re.compile(
    r"(?P<done>\d+(?:\.\d+)?)\s*(?P<du>GiB|MiB|KiB)\s*/\s*"
    r"(?P<total>\d+(?:\.\d+)?)\s*(?P<tu>GiB|MiB|KiB)",
    re.IGNORECASE,
)
# tqdm/uv: "12.5/25.0 MiB" (single unit suffix)
_BYTE_PAIR_SLASH = re.compile(
    r"(?P<done>\d+(?:\.\d+)?)\s*/\s*(?P<total>\d+(?:\.\d+)?)\s*(?P<unit>GiB|MiB|KiB)",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*%")
_PROGRESS_NM_HINTS = (
    "downloading",
    "installing",
    "prepared",
    "building",
    "resolved",
    "package",
)


def _size_to_bytes(num: float, unit: str) -> int:
    u = unit.lower()
    if u == "gib":
        return int(num * 1024**3)
    if u == "mib":
        return int(num * 1024**2)
    if u == "kib":
        return int(num * 1024)
    return int(num)


def _line_allows_nm_fraction(line: str) -> bool:
    lower = line.lower()
    return any(hint in lower for hint in _PROGRESS_NM_HINTS)


def _parse_byte_pair_fraction(line: str) -> tuple[float, int, int] | None:
    match = _BYTE_PAIR.search(line)
    if match:
        done_b = _size_to_bytes(float(match.group("done")), match.group("du"))
        total_b = _size_to_bytes(float(match.group("total")), match.group("tu"))
    else:
        slash = _BYTE_PAIR_SLASH.search(line)
        if not slash:
            return None
        unit = slash.group("unit")
        done_b = _size_to_bytes(float(slash.group("done")), unit)
        total_b = _size_to_bytes(float(slash.group("total")), unit)
    if total_b <= 0:
        return None
    frac = min(1.0, max(0.0, done_b / total_b))
    return frac, done_b, total_b


def _parse_percent_fraction(line: str) -> float | None:
    match = _PERCENT.search(line)
    if not match:
        return None
    pct = float(match.group("pct"))
    if pct > 100.0:
        return None
    return min(1.0, max(0.0, pct / 100.0))

_lock = threading.Lock()
_install: dict = {
    "running": False,
    "returncode": None,
    "error": None,
    "log_fingerprint": "",
    "log_fingerprint_at": 0.0,
}
_engine_packages_cache: tuple[bool, float] | None = None


def later_flag_path() -> Path:
    return app_dir() / LATER_FLAG_NAME


def pending_model_setup_path() -> Path:
    return app_dir() / MODEL_PENDING_FLAG


def prompt_engine_setup_path() -> Path:
    return app_dir() / PROMPT_ENGINE_SETUP


def set_prompt_engine_setup() -> None:
    prompt_engine_setup_path().write_text("1\n", encoding="utf-8")


def clear_prompt_engine_setup() -> None:
    try:
        prompt_engine_setup_path().unlink(missing_ok=True)
    except OSError:
        logging.debug("could not clear prompt-engine-setup", exc_info=True)


def is_prompt_engine_setup() -> bool:
    return prompt_engine_setup_path().is_file()


def is_pending_model_setup() -> bool:
    return pending_model_setup_path().is_file()


def set_pending_model_setup() -> None:
    pending_model_setup_path().write_text("1\n", encoding="utf-8")


def clear_pending_model_setup() -> None:
    try:
        pending_model_setup_path().unlink(missing_ok=True)
    except OSError:
        logging.debug("could not clear pending model setup flag", exc_info=True)


def dismiss_model_setup() -> None:
    clear_pending_model_setup()


def engine_setup_log_path() -> Path:
    return logs_dir() / ENGINE_SETUP_LOG


def is_later_dismissed() -> bool:
    return later_flag_path().is_file()


def dismiss_engine_setup() -> None:
    later_flag_path().write_text("1\n", encoding="utf-8")
    clear_prompt_engine_setup()


def setup_status_after_dismiss(*, engine: bool = False, model: bool = False) -> dict:
    """Lightweight setup payload after «later» — no engine_packages_ok probe."""
    if engine:
        dismiss_engine_setup()
    if model:
        dismiss_model_setup()
    return {
        "dismissed": is_later_dismissed(),
        "pending_model_setup": is_pending_model_setup(),
        "show_engine_setup_modal": False,
    }


def invalidate_engine_packages_cache() -> None:
    global _engine_packages_cache
    _engine_packages_cache = None


def reset_install_state_for_tests() -> None:
    invalidate_engine_packages_cache()
    with _lock:
        _install["running"] = False
        _install["returncode"] = None
        _install["error"] = None
        _install["log_fingerprint"] = ""
        _install["log_fingerprint_at"] = 0.0


def resolve_uv() -> str | None:
    """System uv on PATH, else bundled {install_root}/bin/uv.exe (installer payload)."""
    found = shutil.which("uv")
    if found:
        return found
    bundled = install_root() / "bin" / "uv.exe"
    if bundled.is_file():
        return str(bundled)
    return None


def engine_packages_ok(python: str | None = None, runner=None) -> bool:
    global _engine_packages_cache
    if python is None:
        from slysh.runtime_env import resolve_engine_subprocess_python

        exe = resolve_engine_subprocess_python()
    else:
        exe = python
    if python is None and runner is None and _engine_packages_cache is not None:
        ok, at = _engine_packages_cache
        if time.monotonic() - at < ENGINE_PACKAGES_CACHE_TTL_S:
            return ok
    run = runner or subprocess.run
    try:
        completed = run(
            [exe, "-c", PROBE_IMPORTS],
            capture_output=True,
            timeout=60,
            check=False,
            **subprocess_no_console_kwargs(),
        )
    except Exception:
        ok = False
    else:
        ok = int(getattr(completed, "returncode", 1) or 0) == 0
    if python is None and runner is None:
        _engine_packages_cache = (ok, time.monotonic())
    return ok


def should_show_engine_setup_modal(*, engine_packages: bool) -> bool:
    try:
        from slysh.compute import is_cloud_only

        cloud_only = is_cloud_only()
    except Exception:
        logging.debug("cloud_only check skipped", exc_info=True)
        cloud_only = False
    if engine_packages:
        if is_prompt_engine_setup():
            clear_prompt_engine_setup()
        return False
    if is_prompt_engine_setup():
        return not cloud_only
    if cloud_only:
        return False
    if is_later_dismissed():
        return False
    return True


def engine_setup_blockers(*, engine_packages: bool) -> list[str]:
    if should_show_engine_setup_modal(engine_packages=engine_packages):
        return []
    blockers: list[str] = []
    if engine_packages and not is_prompt_engine_setup():
        blockers.append("engine_packages")
    try:
        from slysh.compute import is_cloud_only

        if is_cloud_only():
            blockers.append("cloud_only")
    except Exception:
        logging.debug("cloud_only check skipped", exc_info=True)
    if is_later_dismissed() and not is_prompt_engine_setup():
        blockers.append("dismissed")
    return blockers


def _read_log_tail(limit: int = 4000) -> str:
    path = engine_setup_log_path()
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def _parse_size_bytes(size_text: str) -> int | None:
    match = _SIZE_TOKEN.search(size_text.strip())
    if not match:
        return None
    num = float(match.group("num"))
    unit = match.group("unit").lower()
    if unit == "gib":
        return int(num * 1024**3)
    if unit == "mib":
        return int(num * 1024**2)
    if unit == "kib":
        return int(num * 1024)
    return None


def _parse_engine_setup_progress(log_text: str) -> dict:
    base = {
        "active": True,
        "message": "",
        "indeterminate": True,
        "fraction": None,
        "packages_done": 0,
        "packages_total": 0,
        "bytes_done": 0,
        "bytes_total": 0,
        "current_package": "",
        "stalled": False,
    }
    if not log_text.strip():
        return base
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    message = lines[-1] if lines else ""
    package_sizes: dict[str, int] = {}
    downloaded: set[str] = set()

    for line in lines:
        dm = _DOWNLOADED_LINE.match(line)
        if dm:
            name = dm.group("name").strip()
            downloaded.add(name)
            continue
        dl = _DOWNLOADING_LINE.match(line)
        if dl:
            name = dl.group("name").strip()
            size_part = dl.group("size")
            if size_part:
                parsed = _parse_size_bytes(size_part)
                if parsed is not None:
                    package_sizes[name] = parsed
            elif name not in package_sizes:
                package_sizes[name] = 0

    tail_message = message
    for line in reversed(lines[-30:]):
        lower = line.lower()
        if any(
            token in lower
            for token in ("downloading", "installing", "prepared", "built", "resolved")
        ):
            tail_message = line
            break

    for line in reversed(lines[-25:]):
        pair = _parse_byte_pair_fraction(line)
        if pair is not None:
            fraction, bytes_done, bytes_total = pair
            return {
                **base,
                "message": line[:500],
                "indeterminate": False,
                "fraction": fraction,
                "bytes_done": bytes_done,
                "bytes_total": bytes_total,
            }
        pct_frac = _parse_percent_fraction(line)
        if pct_frac is not None:
            return {
                **base,
                "message": line[:500],
                "indeterminate": False,
                "fraction": pct_frac,
            }
        if _line_allows_nm_fraction(line):
            match = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if match:
                num = int(match.group(1))
                den = int(match.group(2))
                if den > 0:
                    fraction = min(1.0, max(0.0, num / den))
                    return {
                        **base,
                        "message": line[:500],
                        "indeterminate": False,
                        "fraction": fraction,
                        "packages_done": num,
                        "packages_total": den,
                    }

    message = tail_message

    all_names = set(package_sizes) | downloaded
    packages_total = len(all_names)
    packages_done = len(downloaded)
    bytes_total = sum(package_sizes.values())
    bytes_done = sum(package_sizes.get(name, 0) for name in downloaded)

    current_package = ""
    last_dl = _DOWNLOADING_LINE.match(message)
    if last_dl:
        current_package = last_dl.group("name").strip()
    elif message.lower().startswith("downloading "):
        current_package = message.split(None, 1)[1].split("(", 1)[0].strip()

    fraction: float | None = None
    indeterminate = True
    if bytes_total > 0:
        fraction = min(1.0, max(0.0, bytes_done / bytes_total))
        indeterminate = False
    elif packages_total > 0:
        fraction = min(1.0, max(0.0, packages_done / packages_total))
        indeterminate = False

    if (
        message.lower().startswith("resolved")
        and packages_done == 0
        and bytes_done == 0
    ):
        fraction = None
        indeterminate = True

    return {
        **base,
        "message": message[:500],
        "indeterminate": indeterminate,
        "fraction": fraction,
        "packages_done": packages_done,
        "packages_total": packages_total,
        "bytes_done": bytes_done,
        "bytes_total": bytes_total,
        "current_package": current_package,
    }


def _first_ready_remote_asr_id() -> str | None:
    """First cloud model that has an API key. Gemini CLI is not a key."""
    from slysh.catalog import list_asr_models

    for item in list_asr_models():
        if item.kind == "http" and item.ready:
            return item.id
    return None


def activate_cloud_only_mode() -> dict:
    from slysh.compute import save_engine_mode, save_asr_id

    dismiss_engine_setup()
    clear_prompt_engine_setup()
    save_engine_mode("cloud_only")
    remote_id = _first_ready_remote_asr_id()
    if remote_id:
        save_asr_id(remote_id)
        return {"needs_provider": False, "asr": remote_id}
    return {"needs_provider": True, "asr": None}


def enable_local_engine_mode() -> None:
    from slysh.compute import save_engine_mode

    save_engine_mode("auto")


FRESH_INSTALL_MARKER = ".fresh-install"


def apply_fresh_install_marker() -> bool:
    """After Setup post-install: reset first-run flags so the engine modal can show again."""
    marker = install_root() / FRESH_INSTALL_MARKER
    if not marker.is_file():
        return False
    try:
        marker.unlink(missing_ok=True)
    except OSError:
        logging.debug("could not remove fresh install marker", exc_info=True)
    try:
        later_flag_path().unlink(missing_ok=True)
    except OSError:
        logging.debug("could not clear later flag on fresh install", exc_info=True)
    try:
        pending_model_setup_path().unlink(missing_ok=True)
    except OSError:
        logging.debug("could not clear pending model flag on fresh install", exc_info=True)
    try:
        from slysh.compute import save_engine_mode

        save_engine_mode("auto")
    except Exception:
        logging.debug("could not reset engine_mode on fresh install", exc_info=True)
    set_prompt_engine_setup()
    return True


def setup_status(python: str | None = None, runner=None) -> dict:
    apply_fresh_install_marker()
    with _lock:
        installing = bool(_install["running"])
        error = _install["error"]
        code = _install["returncode"]
    payload = {
        "engine_packages": engine_packages_ok(python=python, runner=runner),
        "installing": installing,
        "error": error,
        "returncode": code,
        "dismissed": is_later_dismissed(),
        "pending_model_setup": is_pending_model_setup(),
        "log_tail": _read_log_tail(
            ENGINE_SETUP_LOG_TAIL_INSTALL if installing else 4000
        )
        if installing or error
        else "",
        "remote_ready": False,
        "show_engine_setup_modal": False,
        "prompt_engine_setup": is_prompt_engine_setup(),
    }
    try:
        from slysh.providers import any_remote_ready

        payload["remote_ready"] = any_remote_ready()
    except Exception:
        logging.debug("remote provider status skipped", exc_info=True)
    try:
        from slysh.compute import is_cloud_only, load_engine_mode

        mode = load_engine_mode()
        payload["engine_mode"] = mode
        payload["cloud_only"] = is_cloud_only()
    except Exception:
        logging.debug("engine_mode status skipped", exc_info=True)
        payload["engine_mode"] = "auto"
        payload["cloud_only"] = False
    if installing:
        progress = _parse_engine_setup_progress(payload["log_tail"])
        fingerprint = payload["log_tail"][-4096:]
        now = time.monotonic()
        with _lock:
            if fingerprint != _install["log_fingerprint"]:
                _install["log_fingerprint"] = fingerprint
                _install["log_fingerprint_at"] = now
            stalled = now - float(_install["log_fingerprint_at"] or now) >= ENGINE_SETUP_STALL_SECONDS
        progress["stalled"] = stalled
        payload["install_progress"] = progress
    else:
        payload["install_progress"] = None
    payload["show_engine_setup_modal"] = should_show_engine_setup_modal(
        engine_packages=bool(payload["engine_packages"])
    )
    payload["engine_setup_blockers"] = engine_setup_blockers(
        engine_packages=bool(payload["engine_packages"])
    )
    try:
        from slysh.runtime_env import engine_slot_needs_resync

        payload["engine_slot_needs_resync"] = engine_slot_needs_resync()
    except Exception:
        logging.debug("engine slot resync check skipped", exc_info=True)
        payload["engine_slot_needs_resync"] = False
    try:
        from slysh.updates import engine_resync_recommended

        payload["engine_resync_recommended"] = engine_resync_recommended()
    except Exception:
        logging.debug("engine resync hint skipped", exc_info=True)
        payload["engine_resync_recommended"] = False
    return payload


def start_engine_install(
    python: str | None = None,
    runner=None,
    *,
    mark_pending_model: bool = False,
    force: bool = False,
) -> dict:
    if (
        not force
        and engine_packages_ok(python=python, runner=runner)
        and not engine_slot_needs_resync_safe()
    ):
        return setup_status(python=python, runner=runner)
    clear_prompt_engine_setup()
    started = False
    with _lock:
        if not _install["running"]:
            _install["running"] = True
            _install["error"] = None
            _install["returncode"] = None
            _install["log_fingerprint"] = ""
            _install["log_fingerprint_at"] = time.monotonic()
            started = True
    if started:
        if mark_pending_model:
            set_pending_model_setup()
        _spawn_install_thread()
    return setup_status(python=python, runner=runner)


def engine_slot_needs_resync_safe() -> bool:
    try:
        from slysh.runtime_env import engine_slot_needs_resync

        return engine_slot_needs_resync()
    except Exception:
        logging.debug("engine_slot_needs_resync skipped", exc_info=True)
        return False


def start_engine_repair(
    python: str | None = None,
    runner=None,
    *,
    force: bool = False,
) -> dict:
    """Re-run engine ``uv sync`` when lock/slot drifted or probe failed (§7.2 repair)."""
    invalidate_engine_packages_cache()
    try:
        from slysh.compute import is_cloud_only

        if is_cloud_only():
            return setup_status(python=python, runner=runner)
    except Exception:
        logging.debug("cloud_only check skipped for engine repair", exc_info=True)
    needs = force or engine_slot_needs_resync_safe() or not engine_packages_ok(
        python=python, runner=runner
    )
    if not needs:
        return setup_status(python=python, runner=runner)
    return start_engine_install(
        python=python, runner=runner, force=True
    )


def _spawn_install_thread() -> None:
    threading.Thread(target=_run_install, daemon=True).start()


def _run_install() -> None:
    log_path = engine_setup_log_path()
    try:
        uv = resolve_uv()
        if not uv:
            raise RuntimeError(
                "Не найден uv (ни в PATH, ни в папке bin программы). "
                "Переустановите Slysh или положите uv.exe в bin рядом с Slysh.bat."
            )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        root = project_root()
        sync_cmd: list[str] = [uv, *uv_sync_engine_argv()]
        from slysh.runtime_env import (
            ensure_engine_venv,
            engine_sync_subprocess_env,
            use_split_engine_venv,
            write_runtime_manifest,
        )

        sync_env = engine_sync_subprocess_env()
        engine_target: Path | None = None
        if use_split_engine_venv():
            from slysh.runtime_env import resolve_engine_venv_target

            engine_target = resolve_engine_venv_target()
            engine_py = ensure_engine_venv(uv, engine_target)
            sync_cmd.extend(["--python", str(engine_py)])
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                sync_cmd,
                cwd=str(root),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                env=sync_env,
                **subprocess_no_console_kwargs(),
            )
        with _lock:
            _install["returncode"] = proc.returncode
            if proc.returncode != 0:
                _install["error"] = f"uv sync завершился с кодом {proc.returncode}"
            else:
                probe_exe: str | None = None
                if engine_target is not None:
                    from slysh.runtime_env import engine_subprocess_python_for_venv

                    probe_exe = engine_subprocess_python_for_venv(engine_target)
                packages_ok = engine_packages_ok(python=probe_exe)
                if not packages_ok:
                    from slysh.runtime_env import revert_active_engine_venv

                    if revert_active_engine_venv():
                        logging.warning(
                            "engine install failed; reverted to previous_engine_venv"
                        )
                    _install["error"] = (
                        "Пакеты расшифровки не установились в окружение engine "
                        "(torch/gigaam). Закройте VPN и нажмите «Начать загрузку» снова "
                        "или переустановите Slysh."
                    )
                else:
                    _install["error"] = None
                    try:
                        later_flag_path().unlink(missing_ok=True)
                    except OSError:
                        logging.debug("could not clear setup later flag", exc_info=True)
                    try:
                        from slysh.updates import save_lock_fingerprint

                        save_lock_fingerprint()
                        slot = engine_target.name if engine_target is not None else None
                        write_runtime_manifest(active_slot=slot)
                        from slysh.runtime_env import prune_stale_engine_venv_slots

                        prune_stale_engine_venv_slots()
                    except Exception:
                        logging.debug("could not save uv.lock fingerprint", exc_info=True)
    except Exception as exc:
        logging.exception("engine package install failed")
        with _lock:
            _install["error"] = str(exc)
            _install["returncode"] = 1
    finally:
        invalidate_engine_packages_cache()
        with _lock:
            _install["running"] = False
