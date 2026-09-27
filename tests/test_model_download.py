import sys
from pathlib import Path

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.catalog import FASTER_WHISPER_DOWNLOAD_SIZES, GIGAAM_ID
from slysh.db import Database
from slysh.model_download import reset_model_download_state_for_tests


def _isolate_roots(tmp_path, monkeypatch):
    proj = tmp_path / "proj-models"
    proj.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(proj))
    monkeypatch.delenv("BUZZ_MODEL_ROOT", raising=False)
    monkeypatch.delenv("GIGAAM_MODEL_ROOT", raising=False)
    return proj


def test_models_include_downloadable_placeholders(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    data = client.get("/api/models").json()
    local = [item for item in data["items"] if item.get("kind") == "local"]
    ids = {item["id"] for item in local}
    assert GIGAAM_ID in ids
    assert "whisper:small" in ids
    gigaam = next(item for item in local if item["id"] == GIGAAM_ID)
    assert gigaam["ready"] is False
    assert gigaam["downloadable"] is True
    whisper = next(item for item in local if item["id"] == "whisper:small")
    assert whisper["downloadable"] is True
    assert len([item for item in local if item["id"].startswith("whisper:")]) == len(
        FASTER_WHISPER_DOWNLOAD_SIZES
    )


def test_download_starts_gigaam_subprocess(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    monkeypatch.setattr("slysh.api.engine_packages_ok", lambda: True)
    started: list[str] = []

    def fake_start(model_id: str) -> None:
        started.append(model_id)

    monkeypatch.setattr("slysh.api.start_model_download", fake_start)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    response = client.post("/api/model/download")
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert started == [GIGAAM_ID]


def test_download_whisper_spawns_command(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    monkeypatch.setattr("slysh.api.engine_packages_ok", lambda: True)
    captured: list[list[str]] = []

    def fake_thread_start(model_id: str) -> None:
        from slysh.model_download import _download_command

        captured.append(_download_command(model_id))

    monkeypatch.setattr("slysh.api.start_model_download", fake_thread_start)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    response = client.post("/api/model/download", json={"id": "whisper:medium"})
    assert response.status_code == 200
    assert captured[0][:4] == [
        sys.executable,
        "-m",
        "slysh.whisper_download",
        "--id",
    ]
    assert captured[0][-1] == "whisper:medium"


def test_status_includes_model_download_payload(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    reset_model_download_state_for_tests()
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    status = client.get("/api/status").json()
    assert "can_download_local" in status
    assert "model_download" in status
    assert status["model_download"]["active"] is False
    prog = status["model_download"]["progress"]
    assert prog["bytes_done"] == 0
    assert "stalled" in prog


def test_model_download_bytes_estimates_whisper_order():
    from slysh.catalog import model_download_bytes_estimate

    tiny = model_download_bytes_estimate("whisper:tiny")
    medium = model_download_bytes_estimate("whisper:medium")
    gigaam = model_download_bytes_estimate("gigaam")
    assert tiny is not None and medium is not None and gigaam is not None
    assert medium > tiny
    assert model_download_bytes_estimate("whisper:large-v3") > medium


def test_compute_progress_whisper_dir_growth(tmp_path, monkeypatch):
    import time

    from slysh.model_download import compute_model_download_progress, dir_size_bytes

    proj = _isolate_roots(tmp_path, monkeypatch)
    dest = proj / "faster-whisper-small"
    dest.mkdir(parents=True)
    baseline = dir_size_bytes([dest])
    (dest / "weights.bin").write_bytes(b"w" * 50_000)
    progress, _, _ = compute_model_download_progress(
        "whisper:small",
        baseline,
        None,
        0,
        time.monotonic(),
        "Downloading model.bin",
    )
    assert progress["bytes_done"] >= 50_000
    assert progress["bytes_total"] > 0
    assert progress["fraction"] is not None
    assert progress["indeterminate"] is False
    assert progress["message"] == "Downloading model.bin"


def test_parse_log_fraction_fetch_files():
    from slysh.model_download import _FETCH_FILES_UI_CAP, _parse_log_fraction

    sample = "Fetching 6 files: 83%|#########3 | 5/6 [00:02<00:00, 2.68it/s]\n"
    frac = _parse_log_fraction(sample)
    assert frac is not None
    assert frac < 0.2
    assert frac <= _FETCH_FILES_UI_CAP


def test_whisper_progress_last_file_uses_bytes(tmp_path, monkeypatch):
    import time

    from slysh.model_download import compute_model_download_progress

    proj = _isolate_roots(tmp_path, monkeypatch)
    dest = proj / "faster-whisper-base"
    dest.mkdir(parents=True)
    baseline = 0
    (dest / "model.bin").write_bytes(b"x" * 120_000_000)
    log = "Fetching 6 files: 83%|#########3 | 5/6 [00:02<00:00, 2.68it/s]"
    progress, _, _ = compute_model_download_progress(
        "whisper:base",
        baseline,
        None,
        0,
        time.monotonic(),
        log,
        log,
    )
    assert progress["fraction"] is not None
    assert progress["fraction"] > 0.75
    assert progress["fraction"] < 0.99


def test_parse_tqdm_bytes_from_log():
    from slysh.model_download import _parse_tqdm_bytes

    sample = " 37%|##############4 | 159M/428M [19:04<48:15, 97.6kiB/s]\n"
    done, total = _parse_tqdm_bytes(sample)
    assert done is not None and total is not None
    assert total == 428 * 1024**2
    assert done == 159 * 1024**2


def test_compute_progress_gigaam_uses_tqdm(tmp_path, monkeypatch):
    import time

    from slysh.model_download import compute_model_download_progress

    _isolate_roots(tmp_path, monkeypatch)
    log_line = " 35%|###### | 150M/428M [17:34<23:57, 202kiB/s]"
    progress, _, _ = compute_model_download_progress(
        "gigaam",
        0,
        None,
        0,
        time.monotonic(),
        log_line,
        log_line,
    )
    assert progress["bytes_total"] >= 428 * 1024**2
    assert progress["fraction"] is not None
    assert 0.3 < progress["fraction"] < 0.4


def test_whisper_download_size_uses_hf_hub(tmp_path, monkeypatch):
    _isolate_roots(tmp_path, monkeypatch)
    recorded: dict = {}

    class FakeHub:
        @staticmethod
        def snapshot_download(**kwargs):
            recorded.update(kwargs)
            dest = Path(kwargs["local_dir"])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "config.json").write_text("{}", encoding="utf-8")
            (dest / "model.bin").write_bytes(b"w")

    import sys

    monkeypatch.setitem(sys.modules, "huggingface_hub", FakeHub())
    from slysh.whisper_download import download_whisper_size

    download_whisper_size("tiny")
    assert recorded["repo_id"] == "Systran/faster-whisper-tiny"
    assert str(recorded["local_dir"]).endswith("faster-whisper-tiny")
