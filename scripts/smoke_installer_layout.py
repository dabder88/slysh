"""Validate dist/payload before Inno Setup. Run after build-installer-payload.ps1."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(os.environ.get("SLYSH_PAYLOAD_DIR", "")).resolve() if os.environ.get(
    "SLYSH_PAYLOAD_DIR"
) else ROOT / "dist" / "payload"
PYTHON = PAYLOAD / ".venv" / "Scripts" / "python.exe"
HTML = PAYLOAD / "web" / "index.html"
BAT = PAYLOAD / "Slysh.bat"
EXE = PAYLOAD / "Slysh.exe"


def _fail(msg: str) -> int:
    print(f"smoke_installer_layout: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if not PAYLOAD.is_dir():
        return _fail(f"missing directory {PAYLOAD}")

    wheelhouse = PAYLOAD / "wheelhouse"
    wh_count = len(list(wheelhouse.glob("*.whl"))) if wheelhouse.is_dir() else 0
    if wh_count < 10:
        return _fail(f"wheelhouse must have at least 10 wheels, got {wh_count}")
    req_ui = wheelhouse / "requirements-ui.txt"
    if not req_ui.is_file():
        return _fail(f"missing wheelhouse requirements-ui.txt ({req_ui})")
    payload_build = PAYLOAD / "payload-build.txt"
    if not payload_build.is_file():
        return _fail(f"missing payload-build.txt ({payload_build})")
    if not payload_build.read_text(encoding="utf-8").strip():
        return _fail("payload-build.txt is empty")
    if list(wheelhouse.glob("proxy_tools*.whl")) == []:
        return _fail("wheelhouse missing proxy_tools*.whl (offline repair)")
    sdists = list(wheelhouse.glob("*.tar.gz"))
    if sdists:
        return _fail(f"wheelhouse must not contain sdists: {[p.name for p in sdists[:5]]}")

    required = [
        PAYLOAD / "bin" / "ffmpeg.exe",
        PAYLOAD / "bin" / "uv.exe",
        PAYLOAD / "Slysh.bat",
        PAYLOAD / "Slysh.exe",
        PAYLOAD / "pyproject.toml",
        PAYLOAD / "uv.lock",
        PAYLOAD / "src" / "slysh" / "runtime_setup.py",
        PYTHON,
    ]
    for path in required:
        if not path.is_file():
            return _fail(f"missing file {path}")

    html = HTML.read_text(encoding="utf-8")
    for needle in ("btn-download-model", "engine-setup-settings", "btn-install-engine"):
        if needle not in html:
            return _fail(f"web/index.html missing {needle}")

    legacy_js = PAYLOAD / "web" / "js" / "legacy.js"
    if not legacy_js.is_file():
        return _fail(f"missing {legacy_js}")
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from smoke_web_legacy_exports import check_legacy_exports

    dupes = check_legacy_exports(legacy_js)
    if dupes:
        return _fail(f"legacy.js duplicate exports: {dupes}")

    bat_bytes = BAT.read_bytes()
    if b"\r\n" not in bat_bytes and b"\n" in bat_bytes:
        return _fail("Slysh.bat must use CRLF line endings (LF-only breaks cmd.exe)")

    bat = bat_bytes.decode("utf-8")
    if 'PATH=%ROOT%\\bin;%PATH%' not in bat and "PATH=%ROOT%\\bin;%PATH%" not in bat:
        return _fail("Slysh.bat must prepend install bin to PATH")
    if "UV_PYTHON_INSTALL_DIR=%ROOT%\\runtime\\python" not in bat:
        return _fail("Slysh.bat must set UV_PYTHON_INSTALL_DIR to runtime\\python")

    payload_root = PAYLOAD.resolve()
    pyvenv_cfg = PAYLOAD / ".venv" / "pyvenv.cfg"
    if not pyvenv_cfg.is_file():
        return _fail(f"missing {pyvenv_cfg}")
    home_line = None
    for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
        if line.startswith("home = "):
            home_line = line.split("=", 1)[1].strip()
            break
    if not home_line:
        return _fail("pyvenv.cfg missing home = line")
    home_path = Path(home_line)
    if not home_path.is_dir():
        return _fail(f"pyvenv.cfg home is not a directory: {home_path}")
    try:
        home_path.resolve().relative_to(payload_root)
    except ValueError:
        return _fail(
            f"pyvenv.cfg home must be under payload ({payload_root}), got {home_path.resolve()}"
        )
    if "Roaming" in home_line and "uv" in home_line.replace("\\", "/"):
        return _fail(f"pyvenv.cfg must not point at user uv cache: {home_line}")

    runtime_python = PAYLOAD / "runtime" / "python"
    if not runtime_python.is_dir():
        return _fail(f"missing {runtime_python}")
    bundled_pythons = list(runtime_python.glob("cpython-*/python.exe"))
    if not bundled_pythons:
        return _fail(f"no bundled python.exe under {runtime_python}")

    pythonw = PAYLOAD / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.is_file():
        return _fail(f"missing {pythonw} (launcher uses pythonw)")

    proc = subprocess.run(
        [str(pythonw), "-c", "import slysh"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        return _fail(f"pythonw import slysh failed: {err}")

    exe = EXE.read_bytes()
    if len(exe) < 128:
        return _fail("Slysh.exe too small")
    import struct

    e_lfanew = struct.unpack_from("<I", exe, 0x3C)[0]
    subsystem = struct.unpack_from("<H", exe, e_lfanew + 4 + 20 + 68)[0]
    if subsystem != 2:
        return _fail(f"Slysh.exe must be Windows GUI subsystem (2), got {subsystem}")

    proc = subprocess.run(
        [str(PYTHON), "-c", "import torch"],
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return _fail("payload venv must not import torch (light install)")

    proc = subprocess.run(
        [str(PYTHON), "-c", "import slysh"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        return _fail(f"slysh import failed: {err}")

    env = {
        **dict(__import__("os").environ),
        "SLYSH_INSTALL_ROOT": str(PAYLOAD.resolve()),
        "PATH": str((PAYLOAD / "bin").resolve()),
    }
    code = (
        "from pathlib import Path; "
        "from slysh.runtime_setup import resolve_uv; "
        "p=resolve_uv(); "
        "assert p, 'resolve_uv returned None'; "
        "assert Path(p).name.lower() == 'uv.exe', p"
    )
    proc = subprocess.run(
        [str(PYTHON), "-c", code],
        env=env,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        return _fail(f"resolve_uv bundled check failed: {err}")

    with tempfile.TemporaryDirectory(prefix="slysh-payload-move-") as tmp:
        moved = Path(tmp) / "payload"
        shutil.copytree(PAYLOAD, moved)
        env = {
            **os.environ,
            "SLYSH_INSTALL_ROOT": str(moved.resolve()),
            "PATH": str((moved / "bin").resolve()),
        }
        pyw = moved / ".venv" / "Scripts" / "pythonw.exe"
        proc = subprocess.run(
            [str(pyw), "-c", "import slysh"],
            env=env,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            return _fail(f"relocated payload import slysh failed: {err}")

    print("smoke_installer_layout: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
