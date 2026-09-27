from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "Slysh"


def app_dir() -> Path:
    base = os.environ.get("GIGAAM_DESKTOP_HOME")
    if base:
        p = Path(base)
    else:
        p = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return app_dir() / "app.db"


def recordings_dir() -> Path:
    d = app_dir() / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def youtube_dir() -> Path:
    d = app_dir() / "youtube"
    d.mkdir(parents=True, exist_ok=True)
    return d


def youtube_cookies_path() -> Path:
    return youtube_dir() / "cookies.txt"


def logs_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def install_root() -> Path:
    """Directory that holds web/, models/ and slysh.ico.

    SLYSH_INSTALL_ROOT wins when it points at an existing directory.
    Otherwise walk upward from this module to the folder with pyproject.toml.
    """
    override = os.environ.get("SLYSH_INSTALL_ROOT")
    if override:
        root = Path(override)
        if root.is_dir():
            return root.resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[2]


def project_root() -> Path:
    return install_root()


def web_dir() -> Path:
    return install_root() / "web"


def app_icon_path() -> Path | None:
    path = project_root() / "slysh.ico"
    return path if path.is_file() else None


def has_gigaam_weights(root: Path) -> bool:
    folder = root / "gigaam"
    if not folder.is_dir():
        return False
    return any(folder.glob("*.ckpt")) or any(folder.glob("*.pt"))


def project_models_dir() -> Path:
    override = os.environ.get("GIGAAM_PROJECT_MODELS")
    if override:
        return Path(override)
    return install_root() / "models"


def catalog_roots() -> list[Path]:
    return [project_models_dir()]


def shared_model_roots() -> list[Path]:
    return catalog_roots()


def model_root() -> Path:
    d = project_models_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def gigaam_download_root() -> Path:
    d = model_root() / "gigaam"
    d.mkdir(parents=True, exist_ok=True)
    return d


INSTALL_UI_LOCALE_SEED = ".install-ui-locale"


def install_ui_locale_seed_path() -> Path:
    return install_root() / INSTALL_UI_LOCALE_SEED
