"""Smoke: Slysh.bat preflight + short-lived launch (no pytest)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_slysh_bat_startup: FAIL: {msg}", file=sys.stderr)
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
    """PIDs of Slysh.exe or python/pythonw running slysh.app (best-effort)."""
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
        if "slysh.app" not in line.lower() and ",Slysh.exe," not in line:
            if "Slysh.exe" not in line:
                continue
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return pids


def main() -> int:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return _fail(f"missing dev venv: {python}")

    home = Path(tempfile.mkdtemp(prefix="slysh-bat-smoke-"))
    env = _bat_env(home)

    proc = subprocess.run(
        [str(python), "-c", "import slysh; from slysh.app import webview2_runtime_installed"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return _fail(f"import preflight: {proc.stderr or proc.stdout}")

    from slysh.app import webview2_runtime_installed

    if not webview2_runtime_installed():
        return _fail("WebView2 runtime not installed — Slysh.bat would exit before opening the window")

    bat_path = ROOT / "Slysh.bat"
    raw = bat_path.read_bytes()
    if b"\r\n" not in raw and b"\n" in raw:
        return _fail("Slysh.bat must use CRLF line endings (cmd.exe breaks on LF-only)")

    print("WebView2: OK")
    uses_exe_launcher = (ROOT / "Slysh.exe").is_file()
    before_pids = _slysh_ui_pids()
    print("Launching Slysh.bat (expect UI process for 20s)...")
    try:
        bat = subprocess.Popen(
            ["cmd.exe", "/c", "Slysh.bat"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return _fail(f"could not start Slysh.bat: {exc}")

    deadline = time.time() + 20.0
    while time.time() < deadline:
        new_ui = _slysh_ui_pids() - before_pids
        if new_ui:
            print(f"Slysh UI process up (pids={sorted(new_ui)}) — OK")
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(next(iter(new_ui)))],
                capture_output=True,
                check=False,
            )
            bat.wait(timeout=5)
            return 0
        code = bat.poll()
        if code is not None:
            if uses_exe_launcher and code == 0:
                time.sleep(0.5)
                continue
            return _fail(f"Slysh.bat exited early with code {code}")
        time.sleep(0.25)

    return _fail("no Slysh UI process within 20s")


if __name__ == "__main__":
    raise SystemExit(main())
