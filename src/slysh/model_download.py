from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from slysh.catalog import (
    GIGAAM_ID,
    is_downloadable_local_id,
    model_download_bytes_estimate,
    model_download_watch_paths,
    whisper_size_from_model_id,
)
from slysh.paths import logs_dir, project_models_dir
from slysh.subprocess_win import subprocess_no_console_kwargs
from slysh.whisper_download import model_download_log_path

_STALL_SECONDS = 90.0
_LOG_TAIL_BYTES = 64 * 1024

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "id": None,
    "error": None,
    "baseline_bytes": 0,
    "progress": None,
}


_DOWNLOAD_LOCK_NAME = "model-download.pid"


def _download_lock_path() -> Path:
    return logs_dir() / _DOWNLOAD_LOCK_NAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_download_lock_pid() -> int | None:
    path = _download_lock_path()
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _clear_stale_download_lock() -> None:
    pid = _read_download_lock_pid()
    if pid is None:
        return
    if _pid_alive(pid):
        return
    try:
        _download_lock_path().unlink(missing_ok=True)
    except OSError:
        pass


def _acquire_download_lock() -> None:
    _clear_stale_download_lock()
    pid = _read_download_lock_pid()
    if pid is not None and _pid_alive(pid):
        raise RuntimeError(
            "Скачивание модели уже идёт (возможно, в другом окне Slysh). "
            "Дождитесь окончания или закройте лишнее окно."
        )
    path = _download_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")


def _release_download_lock() -> None:
    try:
        _download_lock_path().unlink(missing_ok=True)
    except OSError:
        pass


def reset_model_download_state_for_tests() -> None:
    with _lock:
        _state["running"] = False
        _state["id"] = None
        _state["error"] = None
        _state["baseline_bytes"] = 0
        _state["progress"] = None
    _release_download_lock()


def _empty_progress() -> dict[str, Any]:
    return {
        "bytes_done": 0,
        "bytes_total": 0,
        "fraction": None,
        "indeterminate": True,
        "message": "",
        "stalled": False,
    }


def dir_size_bytes(paths: list[Path]) -> int:
    if not paths:
        return 0
    if len(paths) > 1:
        return max(dir_size_bytes([p]) for p in paths)
    total = 0
    base = paths[0]
    if not base.exists():
        return 0
    if base.is_file():
        try:
            return base.stat().st_size
        except OSError:
            return 0
    try:
        for path in base.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _hf_size_token_to_bytes(token: str) -> int | None:
    raw = token.strip().replace(",", "")
    if not raw:
        return None
    mult = 1.0
    unit = ""
    if raw[-2:].lower() == "ib":
        unit = raw[-3:-2].upper()
        num = raw[:-3]
    elif raw[-1].upper() in {"K", "M", "G", "T"}:
        unit = raw[-1].upper()
        num = raw[:-1]
    else:
        num = raw
    if unit == "K":
        mult = 1024.0
    elif unit == "M":
        mult = 1024.0**2
    elif unit == "G":
        mult = 1024.0**3
    elif unit == "T":
        mult = 1024.0**4
    try:
        return int(float(num) * mult)
    except ValueError:
        return None


def _parse_tqdm_bytes(log_text: str) -> tuple[int | None, int | None]:
    """Last tqdm-style ``done/total`` pair from HF hub download lines."""
    if not log_text.strip():
        return None, None
    pattern = re.compile(
        r"(\d+\.?\d*(?:[kKmMgGtT]?iB|[kKmMgGtT]?))\s*/\s*(\d+\.?\d*(?:[kKmMgGtT]?iB|[kKmMgGtT]?))",
    )
    for line in reversed(log_text.splitlines()):
        if "|" not in line:
            continue
        matches = pattern.findall(line)
        if not matches:
            continue
        done_tok, total_tok = matches[-1]
        done_b = _hf_size_token_to_bytes(done_tok)
        total_b = _hf_size_token_to_bytes(total_tok)
        if done_b is not None and total_b is not None and total_b > 0:
            return done_b, total_b
    return None, None


_FETCH_FILES_UI_CAP = 0.12  # доля UI на мелкие файлы до основного веса


def _parse_fetch_files_state(log_text: str) -> tuple[int, int] | None:
    """Последняя строка ``Fetching N files: … done/total …``."""
    if not log_text.strip():
        return None
    for line in reversed(log_text.splitlines()[-40:]):
        if "fetching" not in line.lower():
            continue
        m = re.search(
            r"Fetching\s+(\d+)\s+files?:.*?(\d+)/(\d+)",
            line,
            re.I,
        )
        if not m:
            continue
        total = int(m.group(3))
        done = int(m.group(2))
        if total > 0 and done >= 0:
            return done, total
    return None


def _parse_log_fraction(log_text: str) -> float | None:
    """Best progress fraction from HF tqdm lines (bytes, % or file batch)."""
    if not log_text.strip():
        return None
    best: float | None = None
    fetch_state = _parse_fetch_files_state(log_text)
    if fetch_state:
        done, total = fetch_state
        if done >= total:
            best = _FETCH_FILES_UI_CAP
        elif done == total - 1:
            best = _FETCH_FILES_UI_CAP * (done / total)
        else:
            best = _FETCH_FILES_UI_CAP * done / total

    for line in reversed(log_text.splitlines()[-50:]):
        stripped = line.strip()
        if not stripped:
            continue
        if "fetching" in stripped.lower() and re.search(r"\d+/(\d+)\s*\[", stripped):
            continue
        m = re.match(r"(\d+)%\|", stripped)
        if m:
            val = int(m.group(1)) / 100.0
            best = val if best is None else max(best, val)
        done_b, total_b = _parse_tqdm_bytes(stripped)
        if done_b is not None and total_b and total_b > 0:
            val = done_b / total_b
            best = val if best is None else max(best, val)
    return best


def _pick_log_line(log_text: str) -> str:
    if not log_text.strip():
        return ""
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    for line in reversed(lines[-30:]):
        lower = line.lower()
        if any(
            token in lower
            for token in (
                "download",
                "fetching",
                "pulling",
                "snapshot",
                "getting",
                "loading",
            )
        ):
            return line[:500]
        if re.search(r"\d+\.?\d*%|\d+\s*/\s*\d+", line):
            return line[:500]
    return lines[-1][:500] if lines else ""


def _humanize_log_message(raw: str) -> str:
    line = raw.strip()
    if not line:
        return "Скачивание модели…"
    if line.lower() == "done":
        return "Готово"
    m = re.search(r"Fetching\s+(\d+)\s+files?:\s*(\d+)%", line, re.I)
    if m:
        fs = re.search(r"Fetching\s+(\d+)\s+files?:.*?(\d+)/(\d+)", line, re.I)
        if fs:
            done, total = int(fs.group(2)), int(fs.group(3))
            if total > 0 and done == total - 1 and done < total:
                return "Скачивание основного файла модели…"
        return f"Файлы модели: {m.group(2)}%"
    m = re.search(r"Downloading\s+Systran/faster-whisper-(\S+)", line, re.I)
    if m:
        return f"Whisper {m.group(1)}…"
    done_b, total_b = _parse_tqdm_bytes(line)
    if done_b is not None and total_b and total_b > 0:
        pct = int(round(100 * done_b / total_b))
        return f"Веса: {pct}%"
    if "|" in line:
        head = line.split("|", 1)[0].strip()
        if re.match(r"\d+%", head):
            return f"Загрузка: {head}"
    if len(line) > 120:
        return line[:120] + "…"
    return line


def _read_log_tail() -> str:
    log_path = model_download_log_path()
    try:
        raw = log_path.read_bytes()
    except OSError:
        return ""
    if len(raw) > _LOG_TAIL_BYTES:
        raw = raw[-_LOG_TAIL_BYTES:]
    return raw.decode("utf-8", errors="replace")


def compute_model_download_progress(
    model_id: str,
    baseline_bytes: int,
    bytes_done_override: int | None,
    last_bytes_done: int,
    last_growth_monotonic: float,
    log_message: str,
    log_text: str = "",
) -> tuple[dict[str, Any], int, float]:
    paths = model_download_watch_paths(model_id)
    current = dir_size_bytes(paths)
    bytes_done = max(0, current - baseline_bytes)
    if bytes_done_override is not None:
        bytes_done = max(bytes_done, bytes_done_override)

    tqdm_done, tqdm_total = _parse_tqdm_bytes(log_text or log_message)
    bytes_total = model_download_bytes_estimate(model_id) or 0
    if tqdm_total and tqdm_total > 0:
        bytes_total = max(bytes_total, tqdm_total)
        bytes_done = max(bytes_done, min(tqdm_done or 0, bytes_total))

    log_fraction = _parse_log_fraction(log_text or log_message)
    fetch_state = _parse_fetch_files_state(log_text or log_message)

    now = time.monotonic()

    fraction: float | None = None
    indeterminate = True
    if bytes_total > 0:
        byte_fraction = min(1.0, max(0.0, bytes_done / bytes_total))
        if log_fraction is not None:
            fraction = min(1.0, max(byte_fraction, log_fraction))
            if fetch_state:
                done, total = fetch_state
                if done == total - 1 and done < total:
                    main_span = 1.0 - _FETCH_FILES_UI_CAP
                    prep = _FETCH_FILES_UI_CAP * done / total
                    fraction = min(1.0, prep + main_span * byte_fraction)
            bytes_done = max(bytes_done, int(bytes_total * fraction))
        else:
            fraction = byte_fraction
        indeterminate = False
    elif bytes_done > 0:
        indeterminate = True
    elif log_fraction is not None:
        fraction = min(1.0, log_fraction)
        indeterminate = False

    if bytes_done > last_bytes_done:
        last_bytes_done = bytes_done
        last_growth_monotonic = now
    elif log_fraction is not None and bytes_total > 0:
        implied = int(bytes_total * log_fraction)
        if implied > last_bytes_done:
            last_bytes_done = implied
            last_growth_monotonic = now

    stalled = (now - last_growth_monotonic) >= _STALL_SECONDS
    if bytes_done <= 0 and tqdm_done is None and log_fraction is None:
        stalled = False

    message = _humanize_log_message(log_message)

    progress = {
        "bytes_done": bytes_done,
        "bytes_total": bytes_total,
        "fraction": fraction,
        "indeterminate": indeterminate,
        "message": message,
        "stalled": stalled,
    }
    return progress, last_bytes_done, last_growth_monotonic


def _download_python_executable() -> str:
    """Weights download needs engine deps (huggingface_hub, torch, gigaam)."""
    from slysh.runtime_env import resolve_engine_subprocess_python

    return resolve_engine_subprocess_python()


def _download_command(model_id: str) -> list[str]:
    py = _download_python_executable()
    if model_id == GIGAAM_ID:
        return [py, "-m", "slysh.rnnt_backend", "--download-only"]
    size = whisper_size_from_model_id(model_id)
    if size:
        return [
            py,
            "-m",
            "slysh.whisper_download",
            "--id",
            model_id,
        ]
    raise ValueError("Модель не поддерживает скачивание.")


def model_download_active() -> bool:
    with _lock:
        return bool(_state["running"])


def model_download_payload() -> dict:
    with _lock:
        progress = _state.get("progress")
        if progress is None:
            progress = _empty_progress()
        return {
            "active": bool(_state["running"]),
            "id": _state["id"] if _state["running"] else None,
            "error": _state["error"],
            "progress": dict(progress),
        }


def _monitor_model_download_progress() -> None:
    last_bytes_done = 0
    last_growth = time.monotonic()
    while True:
        with _lock:
            if not _state["running"]:
                break
            model_id = _state["id"]
            baseline = int(_state.get("baseline_bytes") or 0)
        if not model_id:
            time.sleep(1.0)
            continue
        log_body = _read_log_tail()
        log_msg = _pick_log_line(log_body)
        progress, last_bytes_done, last_growth = compute_model_download_progress(
            str(model_id),
            baseline,
            None,
            last_bytes_done,
            last_growth,
            log_msg,
            log_body,
        )
        with _lock:
            if _state["running"]:
                _state["progress"] = progress
        time.sleep(1.0)


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_download(model_id: str) -> None:
    log_path = model_download_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = _download_command(model_id)
    try:
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(project_models_dir().parent),
                env=_subprocess_env(),
                check=False,
                **subprocess_no_console_kwargs(),
            )
        with _lock:
            if proc.returncode == 0:
                _state["error"] = None
                total = model_download_bytes_estimate(model_id) or 0
                if total > 0:
                    _state["progress"] = {
                        "bytes_done": total,
                        "bytes_total": total,
                        "fraction": 1.0,
                        "indeterminate": False,
                        "message": "Готово",
                        "stalled": False,
                    }
            else:
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
                except OSError:
                    tail = ""
                msg = tail.strip() or f"Скачивание завершилось с кодом {proc.returncode}"
                _state["error"] = msg
    except Exception as exc:
        with _lock:
            _state["error"] = str(exc)
    finally:
        _release_download_lock()
        with _lock:
            _state["running"] = False
            _state["id"] = None


def start_model_download(model_id: str) -> None:
    wanted = str(model_id or GIGAAM_ID).strip()
    if not is_downloadable_local_id(wanted):
        raise ValueError("Модель не поддерживает скачивание.")
    _acquire_download_lock()
    paths = model_download_watch_paths(wanted)
    baseline = dir_size_bytes(paths)
    with _lock:
        if _state["running"]:
            _release_download_lock()
            raise RuntimeError("Уже идёт скачивание другой модели.")
        _state["running"] = True
        _state["id"] = wanted
        _state["error"] = None
        _state["baseline_bytes"] = baseline
        _state["progress"] = _empty_progress()
        if model_download_bytes_estimate(wanted):
            bt = model_download_bytes_estimate(wanted) or 0
            _state["progress"]["bytes_total"] = bt
            _state["progress"]["indeterminate"] = False
            _state["progress"]["fraction"] = 0.0
    threading.Thread(
        target=_monitor_model_download_progress,
        daemon=True,
        name="slysh-model-download-monitor",
    ).start()
    threading.Thread(
        target=_run_download,
        args=(wanted,),
        daemon=True,
        name="slysh-model-download",
    ).start()
