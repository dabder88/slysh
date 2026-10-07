"""Simulate installed copy: payload without .venv, run offline repair, import slysh."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(os.environ.get("SLYSH_PAYLOAD_DIR", ROOT / "dist" / "payload"))


def _fail(msg: str) -> int:
    print(f"smoke_offline_venv_repair: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if not PAYLOAD.is_dir():
        return _fail(f"missing payload {PAYLOAD}")
    uv = PAYLOAD / "bin" / "uv.exe"
    if not uv.is_file():
        return _fail(f"missing {uv}")

    tmp = Path(tempfile.mkdtemp(prefix="slysh-offline-repair-"))
    try:
        dest = tmp / "install"
        shutil.copytree(PAYLOAD, dest)
        venv = dest / ".venv"
        if venv.is_dir():
            shutil.rmtree(venv)

        sys.path.insert(0, str(ROOT / "src"))
        from slysh.offline_bootstrap import offline_repair_steps

        cache = tmp / "uv-cache"
        cache.mkdir()
        env = os.environ.copy()
        env["UV_CACHE_DIR"] = str(cache)
        env["UV_PYTHON_INSTALL_DIR"] = str(dest / "runtime" / "python")
        env.pop("VIRTUAL_ENV", None)
        env.pop("UV_PROJECT_ENVIRONMENT", None)

        for step in offline_repair_steps(dest):
            proc = subprocess.run(
                [str(uv), *step],
                cwd=dest,
                env=env,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                return _fail(
                    f"uv {' '.join(step)} exit {proc.returncode}\n"
                    f"{proc.stdout}\n{proc.stderr}"
                )

        py = dest / ".venv" / "Scripts" / "python.exe"
        if not py.is_file():
            return _fail(f"missing {py} after repair")
        proc = subprocess.run(
            [str(py), "-c", "import slysh, webview, proxy_tools"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return _fail(f"import failed: {proc.stderr}")
        cfg = dest / ".venv" / "pyvenv.cfg"
        home_line = None
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("home = "):
                home_line = line.split("=", 1)[1].strip()
                break
        if not home_line:
            return _fail("pyvenv.cfg missing home")
        try:
            Path(home_line).resolve().relative_to(dest.resolve())
        except ValueError:
            return _fail(f"pyvenv.cfg home not under install: {home_line}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("smoke_offline_venv_repair: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
