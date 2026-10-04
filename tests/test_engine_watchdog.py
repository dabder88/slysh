from __future__ import annotations

import time

import pytest

from slysh.engine_watchdog import (
    EngineProgressStallError,
    progress_stall_timeout_s,
    run_with_progress_watch,
)


def test_progress_stall_timeout_default():
    assert progress_stall_timeout_s() >= 600.0


def test_run_with_progress_watch_completes(monkeypatch):
    calls = {"progress": 0}

    def operation():
        return {"ok": True}

    monkeypatch.setattr(
        "slysh.engine_watchdog.progress",
        lambda _url: {"phase": "asr", "progress": calls["progress"]},
    )
    monkeypatch.setattr("slysh.engine_watchdog.cancel", lambda _url: None)
    assert run_with_progress_watch(
        "http://127.0.0.1:9",
        operation,
        stall_timeout_s=1.0,
        poll_s=0.05,
    ) == {"ok": True}


def test_run_with_progress_watch_cancels_on_stall(monkeypatch):
    cancelled: list[str] = []

    def slow():
        time.sleep(2.0)
        return {}

    monkeypatch.setattr(
        "slysh.engine_watchdog.progress",
        lambda _url: {"phase": "asr", "progress": 0.1},
    )
    monkeypatch.setattr(
        "slysh.engine_watchdog.cancel",
        lambda url: cancelled.append(url),
    )
    with pytest.raises(EngineProgressStallError):
        run_with_progress_watch(
            "http://127.0.0.1:9",
            slow,
            stall_timeout_s=0.15,
            poll_s=0.05,
        )
    assert cancelled == ["http://127.0.0.1:9"]
