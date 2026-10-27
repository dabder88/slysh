import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "publish_release_assets.py"
_spec = importlib.util.spec_from_file_location("publish_release_assets", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

release_upload_plan = _mod.release_upload_plan
SETUP_ASSET_NAME_EN = _mod.SETUP_ASSET_NAME_EN
SETUP_ASSET_NAME_RU = _mod.SETUP_ASSET_NAME_RU


def test_release_upload_plan_four_assets(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    ru = dist / "Slysh-Setup-1.0.4-ru.exe"
    en = dist / "Slysh-Setup-1.0.4-en.exe"
    ru.write_bytes(b"ru")
    en.write_bytes(b"en")

    plan = release_upload_plan("1.0.4", dist)
    names = [name for _, name in plan]
    assert names == [
        "Slysh-Setup-1.0.4-ru.exe",
        "Slysh-Setup-1.0.4-en.exe",
        SETUP_ASSET_NAME_RU,
        SETUP_ASSET_NAME_EN,
    ]
    assert plan[0][0] == plan[2][0] == ru
    assert plan[1][0] == plan[3][0] == en
