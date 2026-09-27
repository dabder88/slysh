from __future__ import annotations

import pytest


def test_log_startup_crash_writes_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    (install / "pyproject.toml").write_text("[project]\nname = \"slysh\"\n", encoding="utf-8")
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))

    from slysh.app import log_startup_crash

    try:
        raise RuntimeError("boom-startup")
    except RuntimeError as exc:
        log_startup_crash(exc)

    crash_log = home / "logs" / "startup-crash.log"
    assert crash_log.is_file()
    text = crash_log.read_text(encoding="utf-8")
    assert "RuntimeError: boom-startup" in text
    assert "Traceback" in text

    err_file = install / "launch-last-error.txt"
    assert err_file.is_file()
    assert "startup crash" in err_file.read_text(encoding="utf-8")


def test_main_guard_exits_one(tmp_path, monkeypatch):
    home = tmp_path / "home"
    install = tmp_path / "install"
    install.mkdir()
    (install / "pyproject.toml").write_text("[project]\nname = \"slysh\"\n", encoding="utf-8")
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(install))

    import slysh.app as app_mod

    def boom() -> None:
        raise RuntimeError("guard-boom")

    monkeypatch.setattr(app_mod, "main", boom)
    with pytest.raises(SystemExit) as exc_info:
        try:
            app_mod.main()
        except SystemExit:
            raise
        except BaseException as exc:
            app_mod.log_startup_crash(exc)
            raise SystemExit(1) from exc
    assert exc_info.value.code == 1
    assert (home / "logs" / "startup-crash.log").is_file()
