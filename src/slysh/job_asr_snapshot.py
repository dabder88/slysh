"""Pin ASR model on job start; resume uses the pinned id (plan-fix-2 §5.3)."""
from __future__ import annotations

from slysh.catalog import ModelItem, get_model
from slysh.compute import load_asr_id
from slysh.db import Database
from slysh.providers import REMOTE_BACKENDS


def current_asr_model() -> ModelItem | None:
    return get_model(load_asr_id())


def pin_job_asr_snapshot(db: Database, job_id: int) -> None:
    item = current_asr_model()
    if item is not None:
        db.set_job_asr_snapshot(job_id, item.id, item.backend)


def begin_file_transcription(
    db: Database, job_id: int, *, reset_progress: bool = True
) -> None:
    db.begin_transcription(job_id, reset_progress=reset_progress)
    if reset_progress:
        pin_job_asr_snapshot(db, job_id)


def model_for_job(job: dict) -> ModelItem | None:
    model_id = str(job.get("asr_model_id") or "").strip()
    if model_id:
        pinned = get_model(model_id)
        if pinned is not None:
            return pinned
    return current_asr_model()


def job_uses_remote_asr(job: dict) -> bool:
    item = model_for_job(job)
    return item is not None and item.backend in REMOTE_BACKENDS
