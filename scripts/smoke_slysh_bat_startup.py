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
    env["GIGAAM_DESKTOP_HOME"] = str(home)
    env["GIGAAM_SKIP_ENGINE"] = "1"
    env.pop("GIGAAM_UI_AUTH", None)
    env.pop("GIGAAM_LOOPBACK_STRICT", None)
    return env


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

    print("WebView2: OK")
    print("Launching Slysh.bat (expect timeout while UI is up)...")
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
        code = bat.poll()
        if code is not None:
            return _fail(f"Slysh.bat exited early with code {code}")
        time.sleep(0.25)

    print("Slysh.bat still running after 20s — OK")
    bat.terminate()
    try:
        bat.wait(timeout=5)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(bat.pid)],
            capture_output=True,
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
