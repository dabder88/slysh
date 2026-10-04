"""WebView2 redist filenames and size checks (installer / Setup)."""
from __future__ import annotations

from pathlib import Path

BOOTSTRAPPER_NAME = "MicrosoftEdgeWebview2Setup.exe"
STANDALONE_INSTALLER_NAME = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
MIN_BOOTSTRAPPER_BYTES = 64 * 1024
MIN_STANDALONE_BYTES = 40 * 1024 * 1024


def is_standalone_installer(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < MIN_STANDALONE_BYTES:
        return False
    try:
        head = path.read_bytes()[:2]
    except OSError:
        return False
    return head == b"MZ"


def is_bootstrapper(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < MIN_BOOTSTRAPPER_BYTES or size >= MIN_STANDALONE_BYTES:
        return False
    try:
        head = path.read_bytes()[:2]
    except OSError:
        return False
    return head == b"MZ"


def bundled_installer_candidates(install_root: Path) -> tuple[Path, ...]:
    return (
        install_root / "redist" / STANDALONE_INSTALLER_NAME,
        install_root / STANDALONE_INSTALLER_NAME,
    )
