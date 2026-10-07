from __future__ import annotations

import os
import shutil
import subprocess
import sys
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from slysh.offline_bootstrap import (
    LEGACY_OFFLINE_UV_SYNC_FLAGS,
    OFFLINE_PIP_SYNC_FLAGS,
    UI_REQUIREMENTS_FILENAME,
    offline_pip_sync_ready,
    offline_repair_steps,
    requirements_ui_path,
    uv_pip_sync_argv,
    uv_sync_argv,
    wheelhouse_ready,
)

ROOT = Path(__file__).resolve().parents[1]


def _download_idna_wheel(wh: Path) -> None:
    dest = wh / "idna-3.10-py3-none-any.whl"
    if dest.is_file() and dest.stat().st_size > 1000:
        return
    try:
        meta = json.loads(
            urllib.request.urlopen("https://pypi.org/pypi/idna/3.10/json", timeout=30).read()
        )
        wheel_url = next(
            u["url"]
            for u in meta["urls"]
            if u.get("packagetype") == "bdist_wheel" and u.get("filename", "").endswith(".whl")
        )
        urllib.request.urlretrieve(wheel_url, dest)
    except (urllib.error.URLError, TimeoutError, StopIteration, KeyError) as exc:
        pytest.skip(f"wheel fixture unavailable: {exc}")


def test_offline_pip_sync_argv_when_requirements_ui(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "a.whl").write_bytes(b"x")
    (wh / UI_REQUIREMENTS_FILENAME).write_text("idna==3.10\n", encoding="utf-8")
    args = uv_sync_argv(tmp_path / "bin" / "uv.exe", tmp_path)
    assert args[0:2] == ["pip", "sync"]
    for flag in OFFLINE_PIP_SYNC_FLAGS:
        assert flag in args
    assert str(wh) in args
    assert str(requirements_ui_path(tmp_path)) in args


def test_offline_repair_steps_pip_includes_venv_when_missing(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "a.whl").write_bytes(b"x")
    (wh / UI_REQUIREMENTS_FILENAME).write_text("x\n", encoding="utf-8")
    steps = offline_repair_steps(tmp_path)
    assert len(steps) == 2
    assert steps[0][0] == "venv"
    assert steps[1][0:2] == ["pip", "sync"]


def test_offline_repair_steps_pip_skips_venv_when_present(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "a.whl").write_bytes(b"x")
    (wh / UI_REQUIREMENTS_FILENAME).write_text("x\n", encoding="utf-8")
    py = tmp_path / ".venv" / "Scripts"
    py.mkdir(parents=True)
    (py / "python.exe").write_bytes(b"")
    steps = offline_repair_steps(tmp_path)
    assert len(steps) == 1
    assert steps[0][0:2] == ["pip", "sync"]


def test_legacy_uv_sync_argv_when_wheelhouse_only(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "a.whl").write_bytes(b"x")
    args = uv_sync_argv(tmp_path / "uv.exe", tmp_path)
    assert args[0] == "sync"
    for flag in LEGACY_OFFLINE_UV_SYNC_FLAGS:
        assert flag in args


def test_uv_sync_argv_online_without_wheelhouse(tmp_path: Path):
    assert uv_sync_argv(tmp_path / "uv.exe", tmp_path) == ["sync"]


def test_slysh_bat_offline_pip_sync_contract():
    bat = (ROOT / "Slysh.bat").read_text(encoding="utf-8")
    assert "requirements-ui.txt" in bat
    assert "pip sync" in bat
    assert "--no-index" in bat


def test_launcher_c_offline_wheelhouse_contract():
    src = (ROOT / "launcher" / "Slysh.c").read_text(encoding="utf-8")
    assert "wheelhouse_has_wheels" in src
    assert "wheelhouse_has_requirements_ui" in src
    assert "pip sync" in src
    assert "--no-index" in src


def test_e6_probe_flags_match_module(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    for i in range(10):
        (wh / f"p{i}.whl").write_bytes(b"x")
    (wh / UI_REQUIREMENTS_FILENAME).write_text("pkg==1\n", encoding="utf-8")
    assert wheelhouse_ready(tmp_path, min_wheels=10)
    assert offline_pip_sync_ready(tmp_path, min_wheels=10)
    args = uv_sync_argv(tmp_path / "uv.exe", tmp_path)
    assert args[0] == "pip"


@pytest.mark.skipif(
    os.environ.get("SLYSH_PYTEST_GATE") == "1",
    reason="gate: no PyPI download (SLYSH_PYTEST_GATE)",
)
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_offline_pip_sync_installs_from_wheelhouse(tmp_path: Path):
    uv = shutil.which("uv")
    assert uv is not None
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    cache = tmp_path / "uv-cache"
    cache.mkdir()
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(cache)
    _download_idna_wheel(wh)
    (wh / UI_REQUIREMENTS_FILENAME).write_text("idna==3.10\n", encoding="utf-8")
    for step in offline_repair_steps(tmp_path):
        subprocess.run([uv, *step], cwd=tmp_path, env=env, check=True)
    venv_py = tmp_path / ".venv" / "Scripts" / "python.exe"
    subprocess.run([str(venv_py), "-c", "import idna; assert idna.__version__"], check=True)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_offline_pip_sync_fails_without_wheel(tmp_path: Path):
    uv = shutil.which("uv")
    assert uv is not None
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / UI_REQUIREMENTS_FILENAME).write_text("idna==3.10\n", encoding="utf-8")
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(tmp_path / "uv-cache")
    subprocess.run([uv, "venv", str(tmp_path / ".venv"), "--python", sys.executable], check=True, env=env)
    args = uv_pip_sync_argv(tmp_path)
    proc = subprocess.run([uv, *args], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert proc.returncode != 0
