"""pytest wrapper for scripts/smoke_installer_layout.py (skips if payload missing)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "dist" / "payload"
ISS = ROOT / "installer" / "Slysh.iss"
SMOKE = ROOT / "scripts" / "smoke_installer_layout.py"


def test_inno_script_has_finish_wizard_options():
    text = ISS.read_text(encoding="utf-8")
    assert "[Tasks]" in text
    assert "desktopicon" in text
    assert "{autodesktop}" in text
    assert "[Run]" in text
    assert "postinstall" in text
    assert "Slysh.exe" in text
    assert '{app}\Slysh.exe' in text or "{app}\\Slysh.exe" in text
    assert "runascurrentuser" in text
    run_section = text.split("[Run]")[1].split("[UninstallDelete]")[0]
    assert "{cmd}" not in run_section
    assert "MicrosoftEdgeWebview2Setup.exe" not in run_section
    assert "InstallWebView2IfNeeded" in text
    assert "msedgewebview2.exe" in text
    assert r"EdgeUpdate\ClientState" in text


def test_launcher_isolates_models_catalog_env():
    launcher_c = ROOT / "launcher" / "Slysh.c"
    build_ps1 = ROOT / "scripts" / "build-slysh-launcher.ps1"
    src = launcher_c.read_text(encoding="utf-8")
    script = build_ps1.read_text(encoding="utf-8")
    assert "GIGAAM_PROJECT_MODELS" in src
    assert "UV_PYTHON_INSTALL_DIR" in src
    assert "venv_usable" in src
    assert "run_uv_sync" in src
    assert "find_bundled_python" in src
    assert "launch-last-error.txt" in src
    assert "startup-crash.log" in src
    assert "clear_dev_python_env" in src
    assert "PYTHONPATH" in src
    assert "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in src
    assert "/utf-8" in script


def test_launcher_splash_respects_ui_locale():
    src = (ROOT / "launcher" / "Slysh.c").read_text(encoding="utf-8")
    assert "init_splash_ui_locale" in src
    assert ".install-ui-locale" in src
    assert "settings.json" in src
    assert "ui_locale" in src
    assert "SPLASH_STRINGS_EN" in src


def test_launcher_post_setup_pip_sync_when_locale_seed():
    src = (ROOT / "launcher" / "Slysh.c").read_text(encoding="utf-8")
    assert "install_ui_locale_seed_pending" in src
    assert "run_uv_pip_sync_only" in src
    assert "ensure_payload_venv_sync" in src
    assert "payload pip sync" in src
    seed_idx = src.index("read_install_ui_locale_seed(install_root)")
    settings_idx = src.index("parse_settings_ui_locale(settings_path)")
    assert seed_idx < settings_idx


def test_shell_shows_model_download_controls_without_engine_gate():
    shell = (ROOT / "web" / "js" / "shell.js").read_text(encoding="utf-8")
    assert "asr-model-ready-badge" in shell
    assert "showBtn" in shell
    assert "enginePackages" in shell
    assert "btnEnabled = showBtn && enginePackages" in shell


def test_settings_system_installed_actions_dom():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="settings-dev-tools"' in html
    assert 'id="settings-installed-actions"' in html
    assert "btn-settings-check-updates" in html
    assert "btn-settings-about" in html
    assert "btn-settings-support" in html
    shell = (ROOT / "web" / "js" / "shell.js").read_text(encoding="utf-8")
    assert "syncSystemSettingsActions" in shell
    assert "install_kind" in shell


def test_brand_exclamation_in_sidebar_markup():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "brand-excl-mark" in html
    css = (ROOT / "web" / "styles" / "input.css").read_text(encoding="utf-8")
    assert "#5060ec" in css.lower()


def test_inno_script_excludes_staging_venv_from_install():
    text = ISS.read_text(encoding="utf-8")
    assert ".venv,.venv\\*" in text or ".venv,.venv/*" in text


def test_inno_script_has_uninstall_cleanup():
    text = ISS.read_text(encoding="utf-8")
    assert "InitializeUninstall" in text
    assert ".fresh-install" in text
    assert "KeepModelsOnUninstall" in text
    assert "оставить models" in text
    assert "CurUninstallStepChanged" in text
    assert "DelTree" in text
    assert r"{app}\.venv" in text
    assert r"{app}\runtime" in text
    assert "launch-last-error.txt" in text
    assert "venv-check.log" in text
    assert "RemoveEngineVenvSlots" in text
    assert ".venv-engine-*" in text
    assert "uninsneveruninstall" not in text


def _payload_venv_home_under_payload() -> bool:
    pyvenv_cfg = PAYLOAD / ".venv" / "pyvenv.cfg"
    if not pyvenv_cfg.is_file():
        return False
    home_line = None
    for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
        if line.startswith("home = "):
            home_line = line.split("=", 1)[1].strip()
            break
    if not home_line:
        return False
    try:
        Path(home_line).resolve().relative_to(PAYLOAD.resolve())
        return True
    except ValueError:
        return False


def test_smoke_installer_layout_when_payload_present():
    if not (PAYLOAD / ".venv" / "Scripts" / "python.exe").is_file():
        import pytest

        pytest.skip("dist/payload not built; run scripts/build-installer-payload.ps1")
    if not _payload_venv_home_under_payload():
        import pytest

        pytest.skip(
            "dist/payload .venv points outside payload; rebuild with build-installer-payload.ps1"
        )
    proc = subprocess.run(
        [sys.executable, str(SMOKE)],
        cwd=str(ROOT),
        check=False,
    )
    assert proc.returncode == 0, "smoke_installer_layout failed"
