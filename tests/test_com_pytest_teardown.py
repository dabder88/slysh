"""plan-fix-2 §5.4: pytest COM noise and WASAPI apartment lifecycle."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _repo_conftest():
    path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("slysh_repo_conftest", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pytest_sessionfinish_best_effort_com_teardown():
    _repo_conftest().pytest_sessionfinish(session=None, exitstatus=0)


def test_pytest_sessionfinish_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    _repo_conftest().pytest_sessionfinish(session=None, exitstatus=0)


def test_com_apartment_nested_enter_exits_cleanly():
    if sys.platform != "win32":
        return
    from slysh.wasapi_loopback import _ComApartment

    with _ComApartment():
        pass
    with _ComApartment():
        pass
