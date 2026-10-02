from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slysh.open_paths import resolve_open_target, windows_explorer_reveal_args


def test_windows_explorer_reveal_args_separate_select_and_path():
    raw = r"C:\My files\transcript.srt"
    args = windows_explorer_reveal_args(raw)
    assert args[0] == "explorer"
    assert args[1] == "/select,"
    assert args[2] == str(Path(raw))
    assert len(args) == 3
    assert "/select," not in args[2]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows explorer argv")
def test_windows_explorer_reveal_args_normpath():
    args = windows_explorer_reveal_args("C:/a/b.srt")
    assert args[2] == str(Path("C:/a/b.srt"))


def test_api_open_path_open_file(monkeypatch, tmp_path):
    from slysh.api import create_ui_app
    from slysh.db import Database

    db = Database(tmp_path / "app.db")
    target = tmp_path / "out.srt"
    target.write_text("1", encoding="utf-8")
    opened: list[tuple[str, bool]] = []

    def fake_open_file(path: str) -> None:
        opened.append((path, False))

    def fake_reveal(path: str) -> None:
        opened.append((path, True))

    monkeypatch.setattr("slysh.api.open_file", fake_open_file)
    monkeypatch.setattr("slysh.api.reveal_in_folder", fake_reveal)

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    resp = client.post("/api/open-path", json={"path": str(target), "reveal": False})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert opened == [(str(target), False)]


def test_api_open_path_reveal(monkeypatch, tmp_path):
    from slysh.api import create_ui_app
    from slysh.db import Database

    db = Database(tmp_path / "app.db")
    target = tmp_path / "out.srt"
    target.write_text("1", encoding="utf-8")
    opened: list[tuple[str, bool]] = []

    def fake_open_file(path: str) -> None:
        opened.append((path, False))

    def fake_reveal(path: str) -> None:
        opened.append((path, True))

    monkeypatch.setattr("slysh.api.open_file", fake_open_file)
    monkeypatch.setattr("slysh.api.reveal_in_folder", fake_reveal)

    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    resp = client.post("/api/open-path", json={"path": str(target), "reveal": True})
    assert resp.status_code == 200
    assert opened == [(str(target), True)]


def test_resolve_open_target_existing_file(tmp_path):
    f = tmp_path / "a.srt"
    f.write_text("x", encoding="utf-8")
    assert resolve_open_target(str(f)) == f


def test_resolve_open_target_renamed_single_srt(tmp_path):
    renamed = tmp_path / "new-name.srt"
    renamed.write_text("x", encoding="utf-8")
    stale = tmp_path / "old-name.srt"
    assert resolve_open_target(str(stale)) == renamed


def test_resolve_open_target_missing_parent(tmp_path):
    missing = tmp_path / "nope" / "a.srt"
    with pytest.raises(FileNotFoundError):
        resolve_open_target(str(missing))


def test_resolve_open_target_fallback_to_parent(tmp_path):
    stale = tmp_path / "gone.srt"
    assert resolve_open_target(str(stale)) == tmp_path


def test_db_set_last_export_paths(tmp_path):
    import json

    from slysh.db import Database
    from slysh.models import JobKind

    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\a.wav")
    db.set_last_export_paths(job_id, [r"D:\one.srt", r"E:\two.srt"])
    job = db.get_job(job_id)
    assert job["last_export_path"] == r"E:\two.srt"
    assert json.loads(job["last_export_paths"]) == [r"D:\one.srt", r"E:\two.srt"]


def test_put_last_export_paths_endpoint(tmp_path):
    from slysh.api import create_ui_app
    from slysh.db import Database
    from slysh.models import JobKind

    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, r"C:\a.wav")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    resp = client.put(
        f"/api/jobs/{job_id}/last-export-paths",
        json={"paths": [r"C:\a.srt", r"D:\b.srt"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_export_paths"] == [r"C:\a.srt", r"D:\b.srt"]
    assert body["last_export_path"] == r"D:\b.srt"


def test_reveal_in_folder_launches_explorer_without_no_console(monkeypatch, tmp_path):
    import subprocess as sp

    from slysh.open_paths import reveal_in_folder

    target = tmp_path / "out.srt"
    target.write_text("1", encoding="utf-8")
    seen: list[dict] = []

    def fake_popen(args, **kwargs):
        seen.append({"args": args, "kwargs": kwargs})
        return None

    monkeypatch.setattr("slysh.open_paths.subprocess.Popen", fake_popen)
    reveal_in_folder(str(target))
    assert len(seen) == 1
    assert seen[0]["args"][0] == "explorer"
    assert seen[0]["kwargs"].get("creationflags") != sp.CREATE_NO_WINDOW
    startup = seen[0]["kwargs"].get("startupinfo")
    if startup is not None:
        assert not (startup.dwFlags & sp.STARTF_USESHOWWINDOW)
