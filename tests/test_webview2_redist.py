from __future__ import annotations

from pathlib import Path

from slysh.webview2_redist import (
    MIN_STANDALONE_BYTES,
    STANDALONE_INSTALLER_NAME,
    is_bootstrapper,
    is_standalone_installer,
)


def test_standalone_requires_large_mz(tmp_path: Path):
    small = tmp_path / STANDALONE_INSTALLER_NAME
    small.write_bytes(b"MZ" + b"\0" * 1024)
    assert not is_standalone_installer(small)
    big = tmp_path / "big.exe"
    big.write_bytes(b"MZ" + b"\0" * MIN_STANDALONE_BYTES)
    assert is_standalone_installer(big)


def test_bootstrapper_size_band(tmp_path: Path):
    boot = tmp_path / "boot.exe"
    boot.write_bytes(b"MZ" + b"\0" * (128 * 1024))
    assert is_bootstrapper(boot)
    assert not is_standalone_installer(boot)


def test_slysh_iss_prefers_standalone_when_present():
    iss = (Path(__file__).resolve().parents[1] / "installer" / "Slysh.iss").read_text(
        encoding="utf-8"
    )
    assert "#ifexist" in iss
    assert "MicrosoftEdgeWebView2RuntimeInstallerX64.exe" in iss
