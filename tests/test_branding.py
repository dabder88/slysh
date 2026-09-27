from slysh.paths import app_icon_path, project_root


def test_app_icon_exists_in_repo():
    icon = app_icon_path()
    assert icon is not None
    assert icon.name == "slysh.ico"
    assert icon.is_file()


def test_web_branding_assets_exist():
    root = project_root()
    mark = root / "web" / "branding" / "slysh-mark-48.png"
    favicon = root / "web" / "branding" / "favicon-32.png"
    assert mark.is_file()
    assert favicon.is_file()
