from __future__ import annotations

from pathlib import Path

from slysh.offline_bootstrap import OFFLINE_UV_SYNC_FLAGS, uv_sync_argv, wheelhouse_ready

ROOT = Path(__file__).resolve().parents[1]


def test_uv_sync_argv_offline_when_wheelhouse(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "a.whl").write_bytes(b"x")
    args = uv_sync_argv(tmp_path / "bin" / "uv.exe", tmp_path)
    assert args[0] == "sync"
    for flag in OFFLINE_UV_SYNC_FLAGS:
        assert flag in args
    assert str(wh) in args


def test_uv_sync_argv_online_without_wheelhouse(tmp_path: Path):
    assert uv_sync_argv(tmp_path / "uv.exe", tmp_path) == ["sync"]


def test_slysh_bat_matches_offline_flags():
    bat = (ROOT / "Slysh.bat").read_text(encoding="utf-8")
    for flag in OFFLINE_UV_SYNC_FLAGS:
        assert flag in bat


def test_launcher_c_offline_wheelhouse_contract():
    src = (ROOT / "launcher" / "Slysh.c").read_text(encoding="utf-8")
    assert "wheelhouse_has_wheels" in src
    assert "--offline" in src
    assert "--no-editable" in src


def test_e6_probe_flags_match_module(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    for i in range(10):
        (wh / f"p{i}.whl").write_bytes(b"x")
    assert wheelhouse_ready(tmp_path, min_wheels=10)
    args = uv_sync_argv(tmp_path / "uv.exe", tmp_path)
    assert "--offline" in args
