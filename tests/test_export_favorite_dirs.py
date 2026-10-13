import json

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.compute import settings_path
from slysh.db import Database
from slysh.ui_prefs import (
    MAX_EXPORT_FAVORITE_DIRS,
    load_export_favorite_dirs,
    merge_export_favorite_dirs,
    normalize_export_dirs,
    save_export_favorite_dirs,
)


def test_normalize_export_dirs_dedupe_and_limit():
    raw = [" C:\\a ", "c:\\a", "", "D:\\b"]
    assert normalize_export_dirs(raw) == ["C:\\a", "D:\\b"]
    many = [f"C:\\p{i}" for i in range(20)]
    assert len(normalize_export_dirs(many)) == MAX_EXPORT_FAVORITE_DIRS


def test_export_favorite_dirs_save_load(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    assert load_export_favorite_dirs() == []
    saved = save_export_favorite_dirs(["C:\\exports", "D:\\out"])
    assert saved == ["C:\\exports", "D:\\out"]
    assert load_export_favorite_dirs() == saved
    data = json.loads(settings_path().read_text(encoding="utf-8"))
    assert data["ui"]["export_favorite_dirs"] == saved


def test_merge_export_favorite_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    save_export_favorite_dirs(["C:\\one"])
    merged = merge_export_favorite_dirs(["D:\\two", "c:\\one"])
    assert merged == ["C:\\one", "D:\\two"]


def test_api_export_favorites_get_put(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    assert client.get("/api/ui/export-favorites").json() == {"dirs": []}
    r = client.put(
        "/api/ui/export-favorites",
        json={"dirs": ["C:\\fav", "C:\\fav", "E:\\x"]},
    )
    assert r.status_code == 200
    assert r.json() == {"dirs": ["C:\\fav", "E:\\x"]}
    assert client.get("/api/ui/export-favorites").json() == {"dirs": ["C:\\fav", "E:\\x"]}
