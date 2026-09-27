"""Smoke checks for first-run engine setup modal flags (no GUI)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from slysh.runtime_setup import (
        FRESH_INSTALL_MARKER,
        _parse_engine_setup_progress,
        apply_fresh_install_marker,
        clear_prompt_engine_setup,
        is_later_dismissed,
        is_prompt_engine_setup,
        later_flag_path,
        set_prompt_engine_setup,
        should_show_engine_setup_modal,
    )
    from slysh.paths import install_root

    tmp = Path(tempfile.mkdtemp())
    try:
        home = tmp / "appdata"
        home.mkdir()
        os.environ["GIGAAM_DESKTOP_HOME"] = str(home)

        install = tmp / "install"
        install.mkdir()
        os.environ["SLYSH_INSTALL_ROOT"] = str(install)

        import slysh.runtime_setup as rs

        def fake_packages(**_kw):
            return False

        rs.invalidate_engine_packages_cache()
        rs.engine_packages_ok = fake_packages  # type: ignore[method-assign]

        assert should_show_engine_setup_modal(engine_packages=False) is True

        later_flag_path().write_text("1\n", encoding="utf-8")
        assert should_show_engine_setup_modal(engine_packages=False) is False

        later_flag_path().unlink(missing_ok=True)
        set_prompt_engine_setup()
        later_flag_path().write_text("1\n", encoding="utf-8")
        assert should_show_engine_setup_modal(engine_packages=False) is True

        clear_prompt_engine_setup()
        later_flag_path().unlink(missing_ok=True)

        marker = install_root() / FRESH_INSTALL_MARKER
        marker.write_text("1\n", encoding="utf-8")
        assert apply_fresh_install_marker() is True
        assert is_prompt_engine_setup()
        assert not is_later_dismissed()
        assert not marker.is_file()

        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        assert "engine-packages-confirm-modal" in html
        assert "engine-setup-step-install" in html

        sample = _parse_engine_setup_progress(
            "Downloading torch (3.3GiB)\nDownloading llvmlite\n"
        )
        assert sample.get("bytes_total", 0) > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("verify_engine_setup_modal: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
