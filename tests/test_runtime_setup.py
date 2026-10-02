import concurrent.futures
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.runtime_setup import (
    FRESH_INSTALL_MARKER,
    PROBE_IMPORTS,
    PROMPT_ENGINE_SETUP,
    _parse_engine_setup_progress,
    _run_install,
    apply_fresh_install_marker,
    uv_sync_engine_argv,
    clear_prompt_engine_setup,
    engine_packages_ok,
    is_later_dismissed,
    is_prompt_engine_setup,
    is_pending_model_setup,
    later_flag_path,
    pending_model_setup_path,
    prompt_engine_setup_path,
    reset_install_state_for_tests,
    resolve_uv,
    set_prompt_engine_setup,
    setup_status,
    start_engine_install,
)

BAT_PATH = Path(__file__).resolve().parents[1] / "Slysh.bat"


@pytest.fixture(autouse=True)
def _setup_home(tmp_path, monkeypatch):
    reset_install_state_for_tests()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "gigaam-home"))
    monkeypatch.setattr(
        "slysh.runtime_setup._spawn_install_thread",
        lambda: (_ for _ in ()).throw(AssertionError("uv install thread must not start")),
    )
    yield
    reset_install_state_for_tests()


class _Proc:
    def __init__(self, returncode: int):
        self.returncode = returncode


def test_engine_packages_ok_true_when_subprocess_succeeds():
    seen = []

    def runner(cmd, **kwargs):
        seen.append(list(cmd))
        return _Proc(0)

    assert engine_packages_ok(python="python.exe", runner=runner) is True
    assert seen == [["python.exe", "-c", PROBE_IMPORTS]]


def test_engine_packages_ok_false_when_subprocess_fails():
    def runner(cmd, **kwargs):
        return _Proc(1)

    assert engine_packages_ok(python="python.exe", runner=runner) is False


def test_engine_packages_ok_false_when_subprocess_raises():
    def runner(cmd, **kwargs):
        raise OSError("no python")

    assert engine_packages_ok(python="python.exe", runner=runner) is False


def test_get_setup_does_not_run_uv(tmp_path, monkeypatch):
    cmds = []

    def fake_run(cmd, **kwargs):
        cmds.append(list(cmd))
        name = str(cmd[0]).lower() if cmd else ""
        if name.endswith("uv") or name.endswith("uv.exe") or (len(cmd) > 1 and cmd[1] == "sync"):
            raise AssertionError(f"uv must not start on GET /api/setup: {cmd}")
        return _Proc(1)

    monkeypatch.setattr("slysh.runtime_setup.subprocess.run", fake_run)

    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.get("/api/setup")
    assert response.status_code == 200
    body = response.json()
    assert body["engine_packages"] is False
    assert body["installing"] is False
    assert cmds
    assert cmds[0][1] == "-c"
    assert cmds[0][2] == PROBE_IMPORTS


def test_saved_key_does_not_enable_cloud_only(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    monkeypatch.setattr(
        "slysh.providers.any_remote_ready",
        lambda which=None: True,
    )
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    first = client.get("/api/setup/engine")
    assert first.status_code == 200
    body = first.json()
    assert body["remote_ready"] is True
    assert body["engine_packages"] is False
    assert body["dismissed"] is False
    assert body["cloud_only"] is False
    assert body["engine_mode"] == "auto"
    again = client.get("/api/setup/engine").json()
    assert again["cloud_only"] is False
    assert again["engine_mode"] == "auto"


def test_cloud_only_gemini_binary_still_needs_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    monkeypatch.setattr(
        "slysh.catalog.find_gemini_binary",
        lambda which=None: "gemini.exe",
    )
    monkeypatch.setattr("slysh.catalog.openrouter_api_key", lambda: "")
    monkeypatch.setattr("slysh.providers.http_api_key", lambda _preset_id: "")
    monkeypatch.setattr("slysh.catalog.list_custom_providers", lambda: [])
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    before = client.get("/api/setup/engine").json()
    assert before["cloud_only"] is False
    response = client.post("/api/setup/cloud-only")
    assert response.status_code == 200
    body = response.json()
    assert body["needs_provider"] is True
    assert body["asr"] is None
    assert body["cloud_only"] is True
    from slysh.compute import load_asr_id

    assert load_asr_id() == "gigaam"


def test_post_setup_cloud_only(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    response = client.post("/api/setup/cloud-only")
    assert response.status_code == 200
    body = response.json()
    assert body["dismissed"] is True
    assert body["engine_mode"] == "cloud_only"
    assert body["cloud_only"] is True
    assert body["needs_provider"] is True
    assert app.state.auto_start_engine is False


def test_post_setup_later_sets_dismissed_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.post("/api/setup/later")
    assert response.status_code == 200
    assert response.json()["dismissed"] is True
    assert (tmp_path / "gigaam-home" / "setup-engine-later").is_file()


def test_uv_sync_engine_argv_no_cache(monkeypatch):
    monkeypatch.delenv("SLYSH_ENGINE_INSTALL_NO_CACHE", raising=False)
    assert "--no-cache" not in uv_sync_engine_argv()
    monkeypatch.setenv("SLYSH_ENGINE_INSTALL_NO_CACHE", "1")
    assert "--no-cache" in uv_sync_engine_argv()


def test_run_install_uses_create_no_window_on_windows(monkeypatch, tmp_path):
    import subprocess as sp

    monkeypatch.setattr("slysh.runtime_setup.resolve_uv", lambda: str(tmp_path / "uv.exe"))
    monkeypatch.setattr("slysh.runtime_setup.project_root", lambda: tmp_path)
    monkeypatch.setattr("sys.platform", "win32")
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(kwargs)
        return _Proc(0)

    monkeypatch.setattr("slysh.runtime_setup.subprocess.run", fake_run)
    monkeypatch.setattr("slysh.runtime_setup.engine_packages_ok", lambda: True)
    _run_install()

    assert len(seen) == 1
    assert seen[0]["creationflags"] == sp.CREATE_NO_WINDOW
    assert seen[0]["startupinfo"] is not None


def test_start_engine_install_skips_uv_when_packages_ok():
    def runner(cmd, **kwargs):
        return _Proc(0)

    result = start_engine_install(python="python.exe", runner=runner)
    assert result["engine_packages"] is True
    assert result["installing"] is False


def test_post_setup_engine_starts_background_install(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    started = []
    monkeypatch.setattr(
        "slysh.runtime_setup._spawn_install_thread",
        lambda: started.append(True),
    )
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.post("/api/setup/engine")
    assert response.status_code == 200
    assert response.json()["installing"] is True
    assert len(started) == 1
    reset_install_state_for_tests()


def test_post_setup_engine_mark_pending_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    monkeypatch.setattr("slysh.runtime_setup._spawn_install_thread", lambda: None)
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.post(
        "/api/setup/engine",
        json={"mark_pending_model": True},
    )
    assert response.status_code == 200
    assert response.json()["pending_model_setup"] is True
    assert is_pending_model_setup()
    later = client.post("/api/setup/model-later")
    assert later.status_code == 200
    assert later.json()["pending_model_setup"] is False
    assert not pending_model_setup_path().is_file()
    reset_install_state_for_tests()


def test_parse_engine_setup_progress_fraction():
    log = "line\nDownloading package (3/10)\n"
    parsed = _parse_engine_setup_progress(log)
    assert parsed["fraction"] == pytest.approx(0.3)
    assert parsed["indeterminate"] is False
    assert "3/10" in parsed["message"]


def test_parse_engine_setup_progress_indeterminate():
    parsed = _parse_engine_setup_progress("Resolved 120 packages in 2.1s\n")
    assert parsed["indeterminate"] is True
    assert parsed["fraction"] is None
    assert "Resolved" in parsed["message"]


def test_parse_engine_setup_progress_uv_download_sizes():
    log = (
        "Resolved 80 packages in 3s\n"
        "Downloading torch (3.3GiB)\n"
        "Downloading llvmlite (25.0MiB)\n"
        "Downloading scipy (100MiB)\n"
        "Downloaded scipy\n"
        " Downloading llvmlite\n"
    )
    parsed = _parse_engine_setup_progress(log)
    assert parsed["packages_total"] >= 3
    assert parsed["packages_done"] == 1
    assert parsed["bytes_total"] > 3 * 1024**3
    assert parsed["fraction"] is not None
    assert parsed["indeterminate"] is False
    assert parsed["current_package"]


def test_setup_status_stalled_when_log_unchanged(monkeypatch, tmp_path):
    import time as time_mod

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    log_path = home / "logs" / "engine-setup.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("Downloading torch (3.3GiB)\n", encoding="utf-8")
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    from slysh.runtime_setup import _install, _lock, setup_status

    with _lock:
        _install["running"] = True
        _install["log_fingerprint"] = log_path.read_text(encoding="utf-8")[-4096:]
        _install["log_fingerprint_at"] = time_mod.monotonic() - 120.0

    body = setup_status()
    assert body["installing"] is True
    assert body["install_progress"]["stalled"] is True
    reset_install_state_for_tests()


def test_resolve_uv_prefers_bundled_when_not_on_path(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bundled = bin_dir / "uv.exe"
    bundled.write_bytes(b"stub")
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(tmp_path))
    monkeypatch.setattr("slysh.runtime_setup.shutil.which", lambda _name: None)
    assert resolve_uv() == str(bundled.resolve())


def test_resolve_uv_prefers_system_when_on_path(monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.shutil.which",
        lambda name: "C:\\Tools\\uv.exe" if name == "uv" else None,
    )
    assert resolve_uv() == "C:\\Tools\\uv.exe"


def test_bat_uv_sync_only_when_venv_missing():
    text = BAT_PATH.read_text(encoding="utf-8")
    assert 'if not exist "%PYTHON%" goto :ensure_venv' in text
    assert 'goto :start' in text
    assert 'if exist "%ROOT%\\Slysh.exe"' in text
    ensure_block = text.split("\n:ensure_venv", 1)[1].split("\n:start", 1)[0]
    assert "uv sync" in ensure_block
    label_body = text.split("\n:start", 1)[1]
    assert "uv sync" not in label_body
    light = text.split("uv sync", 1)[0]
    assert "--extra" not in light
    assert "F:\\ProjectsAI" not in text
    assert "buzz-gigaam" not in text
    assert "Slysh-prod-data" not in text
    assert "Giga" + "AMDesktop" not in text
    assert "SLYSH_INSTALL_ROOT=%ROOT%" in text
    assert 'PATH=%ROOT%\\bin;%PATH%' in text


def test_apply_fresh_install_marker_clears_later_flag(monkeypatch, tmp_path):
    from slysh.paths import install_root

    root = tmp_path / "install"
    root.mkdir()
    (root / FRESH_INSTALL_MARKER).write_text("1\n", encoding="utf-8")
    later_flag_path().write_text("1\n", encoding="utf-8")
    monkeypatch.setattr("slysh.runtime_setup.install_root", lambda: root)

    assert apply_fresh_install_marker() is True
    assert not (root / FRESH_INSTALL_MARKER).is_file()
    assert not is_later_dismissed()
    assert is_prompt_engine_setup()


def test_show_engine_setup_modal_e424ae0_without_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    body = client.get("/api/setup").json()
    assert body["show_engine_setup_modal"] is True

    set_prompt_engine_setup()
    body = client.get("/api/setup").json()
    assert body["show_engine_setup_modal"] is True

    response = client.post("/api/setup/later")
    assert response.json()["show_engine_setup_modal"] is False
    assert not is_prompt_engine_setup()


def test_show_engine_setup_modal_dismissed_without_prompt(monkeypatch, tmp_path):
    from slysh.runtime_setup import should_show_engine_setup_modal

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "gigaam-home"))
    later_flag_path().write_text("1\n", encoding="utf-8")
    assert should_show_engine_setup_modal(engine_packages=False) is False


def test_show_engine_setup_modal_prompt_overrides_later(monkeypatch):
    from slysh.runtime_setup import should_show_engine_setup_modal

    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    later_flag_path().write_text("1\n", encoding="utf-8")
    set_prompt_engine_setup()
    assert should_show_engine_setup_modal(engine_packages=False) is True


def test_show_engine_setup_modal_prompt_with_engine_packages(monkeypatch):
    from slysh.runtime_setup import is_prompt_engine_setup, should_show_engine_setup_modal

    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: True,
    )
    set_prompt_engine_setup()
    assert should_show_engine_setup_modal(engine_packages=True) is False
    assert is_prompt_engine_setup() is False


def test_engine_setup_blockers_when_dismissed(monkeypatch, tmp_path):
    from slysh.runtime_setup import engine_setup_blockers

    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    later_flag_path().write_text("1\n", encoding="utf-8")
    blockers = engine_setup_blockers(engine_packages=False)
    assert "dismissed" in blockers


def test_setup_status_applies_fresh_install_marker(monkeypatch, tmp_path):
    root = tmp_path / "install"
    root.mkdir()
    (root / FRESH_INSTALL_MARKER).write_text("1\n", encoding="utf-8")
    monkeypatch.setattr("slysh.runtime_setup.install_root", lambda: root)
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    body = client.get("/api/setup").json()
    assert body["prompt_engine_setup"] is True
    assert body["show_engine_setup_modal"] is True
    assert not (root / FRESH_INSTALL_MARKER).is_file()


def test_start_engine_install_repeat_no_deadlock(monkeypatch):
    """Regression: repeated start/status must not block on _lock (install_repeat_deadlock)."""
    reset_install_state_for_tests()
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )

    def fake_spawn() -> None:
        def worker() -> None:
            time.sleep(0.4)
            reset_install_state_for_tests()

        threading.Thread(target=worker, daemon=True).start()

    monkeypatch.setattr("slysh.runtime_setup._spawn_install_thread", fake_spawn)

    def call_start() -> dict:
        return start_engine_install()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(call_start) for _ in range(3)]
        for fut in concurrent.futures.as_completed(futs, timeout=2.0):
            body = fut.result()
            assert "installing" in body
    reset_install_state_for_tests()


def test_setup_status_concurrent_while_installing_no_deadlock(monkeypatch):
    reset_install_state_for_tests()
    monkeypatch.setattr(
        "slysh.runtime_setup.engine_packages_ok",
        lambda python=None, runner=None: False,
    )
    monkeypatch.setattr("slysh.runtime_setup._spawn_install_thread", lambda: None)
    from slysh.runtime_setup import _install, _lock

    with _lock:
        _install["running"] = True
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futs = [pool.submit(setup_status) for _ in range(12)]
            for fut in concurrent.futures.as_completed(futs, timeout=2.0):
                body = fut.result()
                assert body["installing"] is True
    finally:
        reset_install_state_for_tests()
