"""Wave E.7: engine venv slot name + manifest switch (installed layout)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import slysh.runtime_env as runtime_env


def _fail(msg: str) -> int:
    print(f"smoke_runtime_env_slots: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    fp = "a" * 64
    home = Path(tempfile.mkdtemp(prefix="slysh-rt-"))
    with (
        patch.object(runtime_env, "install_root", return_value=home),
        patch.object(runtime_env, "use_split_engine_venv", return_value=True),
        patch("slysh.updates.uv_lock_fingerprint", return_value=fp),
    ):
        slot = runtime_env.engine_venv_dir_for_fingerprint(fp)
        if slot.name != ".venv-engine-" + ("a" * 16):
            return _fail(f"unexpected slot name {slot.name}")
        runtime_env.write_runtime_manifest(active_slot=slot.name)
        manifest_path = home / runtime_env.RUNTIME_MANIFEST
        if not manifest_path.is_file():
            return _fail("manifest not written")
        data = runtime_env.read_runtime_manifest()
        if data.get("active_engine_venv") != slot.name:
            return _fail(f"manifest active slot {data}")
        if data.get("lock_fingerprint") != fp:
            return _fail("manifest fingerprint")
        runtime_env.write_runtime_manifest(active_slot=".venv-engine-bbbbbbbbbbbbbbbb")
        data2 = runtime_env.read_runtime_manifest()
        if data2.get("previous_engine_venv") != slot.name:
            return _fail(f"expected previous slot, got {data2}")
        prev_scripts = home / slot.name / "Scripts"
        prev_scripts.mkdir(parents=True, exist_ok=True)
        (prev_scripts / "python.exe").write_bytes(b"")
        if not runtime_env.revert_active_engine_venv():
            return _fail("revert_active_engine_venv returned False")
        data3 = runtime_env.read_runtime_manifest()
        if data3.get("active_engine_venv") != slot.name:
            return _fail(f"revert did not restore active slot: {data3}")

    print("smoke_runtime_env_slots: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
