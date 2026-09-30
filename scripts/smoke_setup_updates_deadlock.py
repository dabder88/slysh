"""Smoke: repeated engine install / update download must not deadlock (wave A1)."""
from __future__ import annotations

import concurrent.futures
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_setup_updates_deadlock: FAIL: {msg}", file=sys.stderr)
    return 1


def _install_repeat() -> None:
    from slysh.runtime_setup import (
        reset_install_state_for_tests,
        start_engine_install,
    )

    reset_install_state_for_tests()

    def fake_spawn() -> None:
        def worker() -> None:
            time.sleep(0.35)
            reset_install_state_for_tests()

        threading.Thread(target=worker, daemon=True).start()

    import slysh.runtime_setup as rs

    orig_spawn = rs._spawn_install_thread
    orig_ok = rs.engine_packages_ok
    rs._spawn_install_thread = fake_spawn
    rs.engine_packages_ok = lambda python=None, runner=None: False
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(start_engine_install) for _ in range(3)]
            for fut in concurrent.futures.as_completed(futs, timeout=2.0):
                body = fut.result()
                if "installing" not in body:
                    raise RuntimeError(f"unexpected setup body: {body!r}")
    finally:
        rs._spawn_install_thread = orig_spawn
        rs.engine_packages_ok = orig_ok
        reset_install_state_for_tests()


def _updates_repeat(tmp: Path) -> None:
    import slysh.updates as updates
    from slysh.release_version import installed_app_layout

    installed_app_layout.cache_clear()
    (tmp / "Slysh.exe").write_bytes(b"x")
    (tmp / "runtime" / "python").mkdir(parents=True)
    (tmp / "bin").mkdir(parents=True)
    (tmp / "bin" / "uv.exe").write_bytes(b"x")

    pending = {
        "version": "0.2.0",
        "download_url": "https://objects.githubusercontent.com/setup.exe",
        "size": 100,
        "expected_sha256": "a" * 64,
    }
    with updates._lock:
        updates._state["pending"] = pending
        updates._state["phase"] = "idle"
        updates._state["error"] = None
        updates._state["path"] = None

    def slow_download(_pending: dict) -> None:
        time.sleep(0.35)
        with updates._lock:
            updates._state["phase"] = "ready"
            updates._state["path"] = str(tmp / "setup.exe")

    orig_run = updates._run_download
    orig_enabled = updates.updates_enabled
    updates._run_download = slow_download
    updates.updates_enabled = lambda: True
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(updates.start_download) for _ in range(3)]
            for fut in concurrent.futures.as_completed(futs, timeout=2.0):
                body = fut.result()
                if body["phase"] not in ("downloading", "ready"):
                    raise RuntimeError(f"unexpected download body: {body!r}")
    finally:
        updates._run_download = orig_run
        updates.updates_enabled = orig_enabled
        with updates._lock:
            updates._state["phase"] = "idle"
            updates._state["pending"] = None
    installed_app_layout.cache_clear()


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    import os
    import tempfile

    os.environ.setdefault("GIGAAM_DESKTOP_HOME", tempfile.mkdtemp(prefix="slysh-a1-smoke-"))
    try:
        _install_repeat()
        print("install_repeat: OK")
        tmp = Path(tempfile.mkdtemp(prefix="slysh-a1-upd-"))
        os.environ["SLYSH_INSTALL_ROOT"] = str(tmp)
        _updates_repeat(tmp)
        print("updates_repeat: OK")
    except Exception as exc:
        return _fail(str(exc))
    print("smoke_setup_updates_deadlock: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
