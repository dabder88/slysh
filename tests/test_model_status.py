import logging
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.db import Database


def test_status_reports_missing_model(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "empty-models"))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None)
    client = TestClient(app)
    data = client.get("/api/status").json()
    assert data["model"] == "missing"


def test_status_reports_ready_when_weights_exist(tmp_path, monkeypatch):
    models = tmp_path / "models"
    weight = models / "gigaam" / "e2e_rnnt.ckpt"
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b"ckpt")
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(models))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    assert client.get("/api/status").json()["model"] == "ready"


def test_download_starts_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "empty-models"))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("slysh.api.engine_packages_ok", lambda: True)
    started: list[str] = []

    def fake_start(model_id: str) -> None:
        started.append(model_id)

    monkeypatch.setattr("slysh.api.start_model_download", fake_start)
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.post("/api/model/download")
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert started == ["gigaam"]


def test_download_requires_engine_packages(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "empty-models"))
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("slysh.api.engine_packages_ok", lambda: False)
    db = Database(tmp_path / "app.db")
    client = TestClient(create_ui_app(db=db, engine=None))
    response = client.post("/api/model/download")
    assert response.status_code == 400
    assert "пакет" in response.text.lower() or "torch" in response.text.lower()


def test_download_only_loads_e2e_rnnt(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "models"))
    monkeypatch.setenv("GIGAAM_FORCE_CPU", "1")
    loaded: dict[str, str] = {}

    class FakeGigaam:
        @staticmethod
        def load_model(name, download_root=None, device=None):
            loaded["name"] = name
            loaded["download_root"] = str(download_root)
            loaded["device"] = device
            return object()

    monkeypatch.setitem(sys.modules, "gigaam", FakeGigaam())
    from slysh.rnnt_backend import main

    main(["--download-only"])
    assert loaded["name"] == "e2e_rnnt"
    assert loaded["device"] == "cpu"
    assert Path(loaded["download_root"]) == tmp_path / "models" / "gigaam"


def test_logging_writes_rotating_app_log(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    from slysh.logging_setup import setup_logging
    from slysh.paths import logs_dir

    setup_logging()
    logging.getLogger("slysh").info("hello-log")
    log_path = logs_dir() / "app.log"
    assert log_path.exists()
    assert "hello-log" in log_path.read_text(encoding="utf-8")


def test_logging_drops_webview_color_dump(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    from slysh.logging_setup import setup_logging
    from slysh.paths import logs_dir

    setup_logging()
    logging.getLogger("pywebview").error(
        "window.native.DefaultForeColor.AliceBlue.AntiqueWhite"
    )
    logging.getLogger("slysh").info("keep-me")
    text = (logs_dir() / "app.log").read_text(encoding="utf-8")
    assert "keep-me" in text
    assert "AliceBlue" not in text


def test_ui_has_download_model_button():
    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    legacy_js = (web / "js" / "legacy.js").read_text(encoding="utf-8")
    library_store_js = (web / "js" / "library-store.js").read_text(encoding="utf-8")
    main_js = (web / "js" / "main.js").read_text(encoding="utf-8")
    assert "btn-download-model" in html
    assert "asr-model-ready-badge" in html
    assert "asr-local-model-row" in html
    assert "asr-engine-packages-hint" in html
    assert "/api/model/download" in (web / "js" / "shell.js").read_text(encoding="utf-8")
    assert "btn-download-model" in html
    assert 'name="compute"' in html
    assert "/api/compute" in main_js or "/api/compute" in (web / "js" / "shell.js").read_text(encoding="utf-8")
    assert "job-badge" in legacy_js
    assert "btn-add-files" in html
    assert "batch-target-select" in html
    assert "legacy-files-wrap" in html
    assert "legacy-batches-wrap" in html
    assert "selected_batch_id" in library_store_js
    assert "folder-add-modal" in html
    assert legacy_js.count("let pendingFolderPaths") == 1
    assert "view-dashboard" in html
    assert "view-queue" in html
    assert "editor-layout" in html
    assert "editor-segments" in html
    assert "btn-topbar-export" in html
    assert "queue-metrics" in html
    assert "queue-active-list" in html
    assert "nav-queue" in html
    assert 'class="nav-link is-disabled" data-nav="nav-queue"' not in html
    assert "nav-live" in html
    assert "nav-meeting" in html
    assert "view-meeting" in html
    assert "btn-dashboard-pick-files" in html
    assert "recent-grid" in html
    assert "Открыть файлы" in html
    assert "isLibraryOrphan" in (web / "js" / "library-utils.js").read_text(encoding="utf-8")
    assert "library-table-sort-" in (web / "js" / "library-table.js").read_text(encoding="utf-8")
    assert "move-to-batch-modal" in html
    assert "asr-source" in html
    assert "asr-model-select-local" in html
    assert "asr-provider-field" in html
    assert "openrouter-model" in html
    assert "/api/models" in (web / "js" / "shell.js").read_text(encoding="utf-8")
    assert (web / "js" / "version.js").read_text(encoding="utf-8").find('APP_ASSET_VERSION = "34"') >= 0
    assert (web / "app.css").is_file()


def test_app_js_has_valid_syntax():
    import shutil
    import subprocess

    web = Path(__file__).resolve().parents[1] / "web"
    node = shutil.which("node")
    if not node:
        return
    js_files = [
        web / "js" / "main.js",
        web / "js" / "legacy.js",
        web / "js" / "dashboard.js",
        web / "js" / "queue.js",
        web / "js" / "router.js",
        web / "js" / "shell.js",
        web / "js" / "live.js",
        web / "js" / "meeting.js",
        web / "js" / "editor.js",
        web / "js" / "api.js",
        web / "js" / "library-table.js",
        web / "js" / "library-utils.js",
        web / "js" / "dashboard.js",
    ]
    for path in js_files:
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{path.name}: {result.stderr}"
