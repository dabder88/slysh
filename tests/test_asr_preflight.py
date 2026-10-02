import subprocess

from slysh import api as api_mod
from slysh.catalog import GIGAAM_ID, ModelItem


def test_preflight_missing_downloadable_model(monkeypatch):
    monkeypatch.setattr(
        api_mod,
        "_selected_model",
        lambda: ModelItem(
            id=GIGAAM_ID,
            label="GigaAM",
            backend="rnnt",
            path="",
            ready=False,
            downloadable=True,
        ),
    )
    monkeypatch.setattr(api_mod, "is_cloud_only", lambda: False)
    monkeypatch.setattr(api_mod, "engine_packages_ok", lambda python=None, runner=None: True)
    msg = api_mod._selected_asr_preflight_error()
    assert msg is not None
    assert "не скачана" in msg
    assert "GigaAM" in msg


def test_preflight_remote_not_ready_uses_hint(monkeypatch):
    monkeypatch.setattr(
        api_mod,
        "_selected_model",
        lambda: ModelItem(
            id="http:groq",
            label="Groq",
            backend="http",
            path="",
            ready=False,
            kind="remote",
            hint="Укажите API-ключ Groq.",
        ),
    )
    assert api_mod._selected_asr_preflight_error() == "Укажите API-ключ Groq."


def test_engine_spawn_failure_detail_includes_exit_code():
    proc = subprocess.Popen(["python", "-c", "import sys; sys.exit(3)"])
    proc.wait(timeout=10)
    detail = api_mod._engine_spawn_failure_detail(proc, ["load weights", "torch error"])
    assert "3" in detail
