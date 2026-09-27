from slysh.paths import (
    APP_DIR_NAME,
    catalog_roots,
    gigaam_download_root,
    install_root,
    model_root,
    project_models_dir,
    web_dir,
)


def test_app_dir_name_is_slysh():
    assert APP_DIR_NAME == "Slysh"


def test_model_root_is_project_models(tmp_path, monkeypatch):
    monkeypatch.delenv("BUZZ_MODEL_ROOT", raising=False)
    monkeypatch.delenv("GIGAAM_MODEL_ROOT", raising=False)
    monkeypatch.delenv("GIGAAM_SHARED_MODEL_ROOT", raising=False)
    proj = tmp_path / "proj-models"
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(proj))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert project_models_dir() == proj
    assert catalog_roots() == [proj]
    assert model_root() == proj
    assert gigaam_download_root() == proj / "gigaam"
    assert proj.is_dir()


def test_install_root_sets_models_and_web(tmp_path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()
    monkeypatch.delenv("GIGAAM_PROJECT_MODELS", raising=False)
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    resolved = root.resolve()
    assert install_root() == resolved
    assert project_models_dir() == resolved / "models"
    assert web_dir() == resolved / "web"


def test_project_models_override_wins_over_install_root(tmp_path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()
    models = tmp_path / "elsewhere"
    monkeypatch.setenv("SLYSH_INSTALL_ROOT", str(root))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(models))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert project_models_dir() == models
    assert model_root() == models


def test_ignores_buzz_env(tmp_path, monkeypatch):
    proj = tmp_path / "proj-models"
    other = tmp_path / "buzz"
    other.mkdir()
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(proj))
    monkeypatch.setenv("BUZZ_MODEL_ROOT", str(other))
    monkeypatch.setenv("GIGAAM_MODEL_ROOT", str(other))
    monkeypatch.setenv("GIGAAM_SHARED_MODEL_ROOT", str(other))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert model_root() == proj
    assert catalog_roots() == [proj]
