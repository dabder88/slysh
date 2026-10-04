"""Shared pytest fixtures: isolated app home and import path checks."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_SRC = (_REPO_ROOT / "src").resolve()

# Prefer this repo's sources over an editable install pointing at another tree.
_src = str(_EXPECTED_SRC)
if _src not in sys.path:
    sys.path.insert(0, _src)
_stale = [name for name in sys.modules if name == "slysh" or name.startswith("slysh.")]
for name in _stale:
    del sys.modules[name]


@pytest.fixture(autouse=True)
def _clear_installed_layout_cache():
    from slysh.release_version import installed_app_layout

    installed_app_layout.cache_clear()
    yield
    installed_app_layout.cache_clear()


@pytest.fixture(autouse=True)
def isolated_desktop_home(monkeypatch, tmp_path):
    home = tmp_path / "slysh-home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    import slysh.youtube_ingest as youtube_ingest_mod

    youtube_ingest_mod._meta_db = None
    for key in (
        "GIGAAM_ASR_ID",
        "GIGAAM_ASR_BACKEND",
        "GIGAAM_FORCE_CPU",
        "GIGAAM_SKIP_ENGINE",
        "GIGAAM_UI_AUTH",
        "GIGAAM_LOOPBACK_STRICT",
        "SLYSH_DISABLE_OPENAPI",
        "GIGAAM_ENGINE_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIGAAM_UI_AUTH", "0")
    monkeypatch.setenv("GIGAAM_LOOPBACK_STRICT", "0")
    yield home


@pytest.fixture(autouse=True)
def default_local_asr_ready(monkeypatch, isolated_desktop_home):
    """Local GigaAM on disk + engine packages OK unless a test overrides."""
    from slysh import api as api_mod

    proj = isolated_desktop_home / "proj-models"
    proj.mkdir(exist_ok=True)
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(proj))
    gigaam = proj / "gigaam"
    gigaam.mkdir(parents=True, exist_ok=True)
    (gigaam / "e2e.ckpt").write_bytes(b"ckpt")
    monkeypatch.setattr(api_mod, "engine_packages_ok", lambda: True)


def pytest_sessionstart(session):
    import slysh

    pkg = Path(slysh.__file__).resolve()
    try:
        pkg.relative_to(_EXPECTED_SRC)
    except ValueError as exc:
        raise AssertionError(
            f"tests must import slysh from {_EXPECTED_SRC}, got {pkg}"
        ) from exc


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "network: tests that require external network access",
    )


def pytest_sessionfinish(session, exitstatus):
    """§5.4: best-effort COM teardown on Windows after tests (IUnknown noise).

    Real WASAPI loopback uses _ComApartment in wasapi_loopback.py (CoUninitialize
    on thread exit). Residual messages at process exit are usually benign for the app.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.ole32.CoUninitialize()
    except Exception:
        pass
