"""Wave E.7: engine_slot_needs_resync when manifest fingerprint/slot drifts."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import slysh.runtime_env as runtime_env


def _fail(msg: str) -> int:
    print(f"smoke_engine_slot_resync: FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    fp = "b" * 64
    home = Path(tempfile.mkdtemp(prefix="slysh-resync-"))
    with (
        patch.object(runtime_env, "install_root", return_value=home),
        patch.object(runtime_env, "use_split_engine_venv", return_value=True),
        patch("slysh.updates.uv_lock_fingerprint", return_value=fp),
    ):
        if runtime_env.engine_slot_needs_resync():
            return _fail("expected no resync without manifest")
        runtime_env.write_runtime_manifest(active_slot=".venv-engine-" + ("b" * 16))
        manifest = runtime_env.read_runtime_manifest()
        if manifest.get("lock_fingerprint") != fp:
            return _fail("manifest fingerprint not saved")
        with patch("slysh.updates.uv_lock_fingerprint", return_value="c" * 64):
            if not runtime_env.engine_slot_needs_resync():
                return _fail("expected resync when lock fingerprint changed")
        with patch("slysh.updates.uv_lock_fingerprint", return_value=fp):
            runtime_env.write_runtime_manifest(
                active_slot=".venv-engine-aaaaaaaaaaaaaaaa"
            )
            if not runtime_env.engine_slot_needs_resync():
                return _fail("expected resync when active slot != target")

    print("smoke_engine_slot_resync: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
