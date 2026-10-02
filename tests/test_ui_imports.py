import ast
from pathlib import Path

FORBIDDEN = {"torch", "gigaam", "slysh.rnnt_backend"}

def test_app_and_api_modules_do_not_import_torch():
    root = Path(__file__).resolve().parents[1] / "src" / "slysh"
    for name in (
        "app.py",
        "api.py",
        "db.py",
        "queue.py",
        "runtime_setup.py",
        "runtime_env.py",
        "providers.py",
        "remote_asr.py",
        "gemini_cli.py",
        "meeting_capture.py",
        "wasapi_loopback.py",
        "batch_runner.py",
        "speakers_engine.py",
    ):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in {"torch", "gigaam"}
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("torch")
                assert node.module != "gigaam"
                assert node.module != "slysh.rnnt_backend"
                if name in ("api.py", "batch_runner.py", "speakers_engine.py"):
                    assert node.module != "slysh.speakers_msdd"
