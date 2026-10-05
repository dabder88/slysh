"""R11/R15: UI lifespan stops owned child processes on shutdown."""
from __future__ import annotations

import slysh.api as api_mod
from slysh.api import create_ui_app
from slysh.db import Database


class _RunningProc:
    def poll(self):
        return None


def test_stop_engine_terminates_running_process(tmp_path):
    app = create_ui_app(Database(tmp_path / "app.db"), engine=None)
    proc = _RunningProc()
    app.state.engine_proc = proc
    app.state.engine_url = "http://127.0.0.1:9"
    terminated: list = []
    original = api_mod.terminate_process_tree
    api_mod.terminate_process_tree = lambda p, timeout=8: terminated.append(p)
    try:
        api_mod._stop_engine(app)
    finally:
        api_mod.terminate_process_tree = original
    assert terminated == [proc]
    assert app.state.engine_proc is None
    assert app.state.engine_url is None


def test_shutdown_ui_runtime_calls_stop_engine(tmp_path):
    app = create_ui_app(Database(tmp_path / "app.db"), engine=None)
    calls: list = []
    original = api_mod._stop_engine
    api_mod._stop_engine = lambda a: calls.append(a)
    try:
        api_mod.shutdown_ui_runtime(app)
    finally:
        api_mod._stop_engine = original
    assert calls == [app]
