"""Serialize local engine and remote ASR workers (wave C)."""
from __future__ import annotations

import logging
import threading
import time

from fastapi import FastAPI

from slysh.db import Database
from slysh.models import JobKind, JobStatus

log = logging.getLogger(__name__)


class AsrCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._local_job_id: int | None = None
        self._remote_job_id: int | None = None

    def local_job_id(self) -> int | None:
        with self._lock:
            return self._local_job_id

    def remote_job_id(self) -> int | None:
        with self._lock:
            return self._remote_job_id

    def try_begin_local(self, job_id: int) -> bool:
        with self._lock:
            if self._local_job_id is not None:
                return False
            self._local_job_id = job_id
            return True

    def end_local(self, job_id: int) -> None:
        with self._lock:
            if self._local_job_id == job_id:
                self._local_job_id = None

    def begin_local_wait(self, job_id: int, *, timeout_s: float = 7200.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.try_begin_local(job_id):
                return True
            time.sleep(0.05)
        return False

    def try_begin_remote(self, job_id: int) -> bool:
        with self._lock:
            if self._remote_job_id is not None:
                return False
            self._remote_job_id = job_id
            return True

    def end_remote(self, job_id: int) -> None:
        with self._lock:
            if self._remote_job_id == job_id:
                self._remote_job_id = None

    def begin_remote_wait(self, job_id: int, *, timeout_s: float = 7200.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.try_begin_remote(job_id):
                return True
            time.sleep(0.05)
        return False


def job_run_id(db: Database, job_id: int) -> int:
    job = db.get_job(job_id) or {}
    return int(job.get("run_id") or 0)


def job_run_active(db: Database, job_id: int, run_id: int) -> bool:
    job = db.get_job(job_id) or {}
    if int(job.get("run_id") or 0) != run_id:
        return False
    if job.get("status") == JobStatus.CANCELLED.value:
        return False
    return True


def pump_local_queued(
    app: FastAPI,
    db: Database,
    *,
    is_youtube_job,
    is_remote_model,
    start_engine_job,
) -> None:
    coord: AsrCoordinator = app.state.asr_coordinator
    if coord.local_job_id() is not None:
        return
    for job in db.list_queued_jobs():
        if is_youtube_job(job):
            continue
        if is_remote_model():
            continue
        jid = int(job["id"])
        current = db.get_job(jid) or {}
        if current.get("status") != JobStatus.QUEUED.value:
            continue
        if current.get("kind") not in (JobKind.FILE.value, JobKind.LIVE.value, JobKind.MEETING.value):
            continue
        path = str(job.get("source_path") or "")
        if not path:
            continue
        log.info("pump local ASR queue -> job %s", jid)
        start_engine_job(app, db, jid, path)
        return


def pump_remote_queued(
    app: FastAPI,
    db: Database,
    *,
    is_youtube_job,
    is_remote_model,
    start_remote_job,
) -> None:
    coord: AsrCoordinator = app.state.asr_coordinator
    if coord.remote_job_id() is not None:
        return
    if not is_remote_model():
        return
    for job in db.list_queued_jobs():
        if is_youtube_job(job):
            continue
        jid = int(job["id"])
        current = db.get_job(jid) or {}
        if current.get("status") != JobStatus.QUEUED.value:
            continue
        path = str(job.get("source_path") or "")
        if not path:
            continue
        log.info("pump remote ASR queue -> job %s", jid)
        start_remote_job(app, db, jid, path)
        return
