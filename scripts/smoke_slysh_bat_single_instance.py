"""Smoke: second Slysh.bat while first UI is up must not spawn another instance (C.5)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(
    os.environ.get("SLYSH_SMOKE_ROOT", "")
).resolve() if os.environ.get("SLYSH_SMOKE_ROOT") else Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_slysh_bat_single_instance: FAIL: {msg}", file=sys.stderr)
    return 1


def _bat_env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("SLYSH_") or key in (
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "UV_PYTHON_INSTALL_DIR",
        ):
            del env[key]
    env["GIGAAM_DESKTOP_HOME"] = str(home)
    env["GIGAAM_SKIP_ENGINE"] = "1"
    env.pop("GIGAAM_UI_AUTH", None)
    env.pop("GIGAAM_LOOPBACK_STRICT", None)
    return env


def _slysh_ui_pids() -> set[int]:
    out = subprocess.run(
        [
            "wmic",
            "process",
            "where",
            "name='python.exe' or name='pythonw.exe' or name='Slysh.exe'",
            "get",
            "ProcessId,CommandLine",
            "/FORMAT:CSV",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pids: set[int] = set()
    for line in out.stdout.splitlines():
        low = line.lower()
        if "slysh.app" not in low and "slysh.exe" not in low:
            continue
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return pids


def main() -> int:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return _fail(f"missing venv: {python}")

    from slysh.app import webview2_runtime_installed

    if not webview2_runtime_installed():
        return _fail("WebView2 not installed")

    home = Path(tempfile.mkdtemp(prefix="slysh-single-"))
    env = _bat_env(home)
    before = _slysh_ui_pids()
    first_ui: set[int] = set()
    ui_after: set[int] = set()
    bat1: subprocess.Popen | None = None
    bat2: subprocess.Popen | None = None

    try:
        bat1 = subprocess.Popen(
            ["cmd.exe", "/c", "Slysh.bat"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 25.0
        while time.time() < deadline:
            new_ui = _slysh_ui_pids() - before
            if new_ui:
                first_ui = new_ui
                break
            if bat1.poll() is not None and not (ROOT / "Slysh.exe").is_file():
                return _fail(f"first bat exited early code={bat1.returncode}")
            time.sleep(0.25)
        if not first_ui:
            return _fail("first instance UI did not start")

        ui_before_second = _slysh_ui_pids()
        bat2 = subprocess.Popen(
            ["cmd.exe", "/c", "Slysh.bat"],
            cwd=str(ROOT),
            env=_bat_env(Path(tempfile.mkdtemp(prefix="slysh-single-b-"))),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        bat2.wait(timeout=15)
        time.sleep(1.0)
        ui_after = _slysh_ui_pids()
        extra = ui_after - ui_before_second
        if extra:
            return _fail(f"second launch spawned extra UI pids: {sorted(extra)}")
        if bat2.returncode not in (0, 1):
            return _fail(f"unexpected second bat exit code {bat2.returncode}")

        print("smoke_slysh_bat_single_instance: OK")
        return 0
    finally:
        for pid in first_ui | ui_after:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        for proc in (bat1, bat2):
            if proc is not None and proc.poll() is None:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                )


if __name__ == "__main__":
    raise SystemExit(main())
