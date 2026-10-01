from __future__ import annotations

import importlib
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from slysh.batch_rules import is_youtube_batch_rules, normalize_rules
from slysh.compute import is_cloud_only
from slysh.export import (
    batch_export_stem_candidates,
    suggested_export_path,
    unique_export_path,
    write_job_export,
    youtube_export_meta_from_job,
    youtube_job_export_path,
)
from slysh.models import BatchStatus, JobKind, JobStatus
from slysh.speakers import assign_speakers
from slysh.source_path import require_existing_file
from slysh.youtube_ingest import (
    load_job_ingest_meta,
    load_job_youtube_video,
    save_job_ingest_meta,
    run_youtube_job,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from slysh.db import Database

logger = logging.getLogger(__name__)


class BatchRunnerControl:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.batch_id: int | None = None
        self.pause_after_current = False
        self.cancel_requested = False
        self.current_job_id: int | None = None
        self.thread: threading.Thread | None = None
        self.summary: dict | None = None


def get_runner(app: FastAPI) -> BatchRunnerControl:
    runner = getattr(app.state, "batch_runner", None)
    if runner is None:
        runner = BatchRunnerControl()
        app.state.batch_runner = runner
    return runner


def is_batch_active(app: FastAPI, batch_id: int | None = None) -> bool:
    runner = get_runner(app)
    with runner.lock:
        if runner.batch_id is None:
            return False
        if batch_id is None:
            return True
        return runner.batch_id == batch_id


def _export_batch_job(
    db: Database,
    job_id: int,
    job: dict,
    rules: dict,
    *,
    used_names: set[str] | None = None,
) -> None:
    fmt = str(rules.get("export_fmt") or "srt")
    segments = db.list_segments(job_id)
    export_dirs: list[str] = []
    raw_dirs = rules.get("export_dirs")
    if isinstance(raw_dirs, list):
        export_dirs = [str(d).strip() for d in raw_dirs if str(d).strip()]
    if not export_dirs and rules.get("export_dir_mode") == "fixed" and rules.get("export_dir"):
        export_dirs = [str(rules["export_dir"]).strip()]

    targets: list[dict] = []
    if export_dirs:
        for directory in export_dirs:
            one = dict(rules)
            one["export_dir_mode"] = "fixed"
            one["export_dir"] = directory
            targets.append(one)
    else:
        targets.append(rules)

    last_path: Path | None = None
    all_paths: list[str] = []
    for target_rules in targets:
        if is_youtube_batch_rules(target_rules) or str(job.get("kind") or "") == JobKind.YOUTUBE.value:
            out = youtube_job_export_path(job, fmt, target_rules)
            video = load_job_youtube_video(job_id) or {}
            _, language = load_job_ingest_meta(job_id)
            meta = youtube_export_meta_from_job(job, video, language)
            write_job_export(out, segments, fmt, youtube_meta=meta)
        else:
            if target_rules.get("export_dir_mode") == "fixed" and target_rules.get("export_dir"):
                stems = batch_export_stem_candidates(str(job["source_path"]))
                used = used_names if used_names is not None else set()
                out = unique_export_path(
                    Path(str(target_rules["export_dir"])),
                    stems[0],
                    fmt,
                    used,
                    alt_stems=stems[1:],
                )
            else:
                out = suggested_export_path(job["source_path"], fmt)
            write_job_export(out, segments, fmt, job=job)
        last_path = out
        all_paths.append(str(out))

    if all_paths:
        db.set_last_export_paths(job_id, all_paths)
    elif last_path is not None:
        db.set_last_export_path(job_id, str(last_path))


def _run_youtube_batch_job(
    app: FastAPI,
    db: Database,
    batch_id: int,
    job_id: int,
    job: dict,
    rules: dict,
) -> bool:
    """Returns True if job finished successfully (completed)."""
    runner = get_runner(app)
    url = str(job.get("source_path") or "")
    method = str(rules.get("youtube_method") or "apify")
    language = str(rules.get("youtube_language") or "ru")
    save_job_ingest_meta(job_id, method, language)  # type: ignore[arg-type]

    cancel_event = threading.Event()
    app.state.youtube_cancels[job_id] = cancel_event
    db.begin_transcription(job_id)
    try:
        run_youtube_job(
            db,
            job_id,
            url,
            method,  # type: ignore[arg-type]
            language,
            cancel_event=cancel_event,
        )
    finally:
        app.state.youtube_cancels.pop(job_id, None)

    current = db.get_job(job_id) or {}
    if current.get("status") == JobStatus.CANCELLED.value:
        return False
    if current.get("status") != JobStatus.COMPLETED.value:
        return False

    if rules.get("export"):
        try:
            refreshed = db.get_job(job_id) or job
            _export_batch_job(db, job_id, refreshed, rules)
        except Exception as exc:
            logging.exception("batch export failed for job %s", job_id)
            db.set_error(job_id, str(exc))

    with runner.lock:
        if runner.pause_after_current:
            db.update_batch(batch_id, status=BatchStatus.PAUSED)
            return True
    return True


def _batch_pause_on_error(
    runner: BatchRunnerControl,
    db: Database,
    batch_id: int,
    *,
    done: int,
    failed: int,
    skipped: int,
) -> None:
    db.update_batch(batch_id, status=BatchStatus.PAUSED)
    runner.summary = {
        "done": done,
        "failed": failed,
        "skipped": skipped,
        "paused": True,
        "pause_reason": "on_error_stop",
    }


def start_batch(
    app: FastAPI,
    db: Database,
    batch_id: int,
    *,
    run_file_job: Callable[[FastAPI, Database, int, str], None],
    ensure_engine: Callable[[FastAPI], str] | None = None,
    run_engine_job: Callable[[Database, str, int, str], None] | None = None,
    engine_cancel: Callable[[str], None],
) -> None:
    runner = get_runner(app)
    with runner.lock:
        if runner.batch_id is not None:
            raise RuntimeError("Уже выполняется другой пакет")
        runner.batch_id = batch_id
        runner.pause_after_current = False
        runner.cancel_requested = False
        runner.summary = None

    db.update_batch(batch_id, status=BatchStatus.RUNNING)

    def work() -> None:
        done = 0
        failed = 0
        skipped = 0
        try:
            batch = db.get_batch(batch_id)
            if batch is None:
                return
            rules = normalize_rules(batch.get("rules"))
            youtube_batch = is_youtube_batch_rules(rules)
            engine_url: str | None = getattr(app.state, "engine_url", None)
            export_used: set[str] = set()
            delay_s = int(rules.get("delay_seconds") or 0)
            job_list = db.list_batch_jobs(batch_id)
            total_jobs = len(job_list)

            for index, job in enumerate(job_list):
                job_id = int(job["id"])
                with runner.lock:
                    if runner.cancel_requested:
                        if job["status"] in (
                            JobStatus.IDLE.value,
                            JobStatus.QUEUED.value,
                        ):
                            db.set_status(job_id, JobStatus.CANCELLED)
                        continue
                    if runner.pause_after_current:
                        db.update_batch(batch_id, status=BatchStatus.PAUSED)
                        runner.summary = {
                            "done": done,
                            "failed": failed,
                            "skipped": skipped,
                            "paused": True,
                        }
                        return
                    runner.current_job_id = job_id

                if rules["skip_completed"] and job["status"] == JobStatus.COMPLETED.value:
                    skipped += 1
                    continue

                with runner.lock:
                    if runner.cancel_requested:
                        db.set_status(job_id, JobStatus.CANCELLED)
                        continue

                if youtube_batch:
                    ok = _run_youtube_batch_job(app, db, batch_id, job_id, job, rules)
                    current = db.get_job(job_id) or {}
                    if current.get("status") == JobStatus.CANCELLED.value:
                        continue
                    if not ok:
                        failed += 1
                        if rules.get("on_error") == "stop":
                            _batch_pause_on_error(
                                runner,
                                db,
                                batch_id,
                                done=done,
                                failed=failed,
                                skipped=skipped,
                            )
                            return
                        continue
                    done += 1
                    with runner.lock:
                        if runner.pause_after_current:
                            runner.summary = {
                                "done": done,
                                "failed": failed,
                                "skipped": skipped,
                                "paused": True,
                            }
                            return
                    if delay_s > 0 and index < total_jobs - 1:
                        time.sleep(delay_s)
                    continue

                try:
                    source = require_existing_file(job["source_path"])
                except ValueError as exc:
                    db.set_error(job_id, str(exc))
                    db.set_status(job_id, JobStatus.FAILED)
                    failed += 1
                    if rules.get("on_error") == "stop":
                        _batch_pause_on_error(
                            runner,
                            db,
                            batch_id,
                            done=done,
                            failed=failed,
                            skipped=skipped,
                        )
                        return
                    continue

                db.begin_transcription(job_id)
                try:
                    current = db.get_job(job_id) or {}
                    if current.get("status") == JobStatus.CANCELLED.value:
                        continue
                    run_file_job(app, db, job_id, str(source))
                except Exception as exc:
                    logging.exception("batch job %s failed", job_id)
                    detail = getattr(exc, "detail", None)
                    db.set_error(job_id, str(detail or exc))
                    db.set_status(job_id, JobStatus.FAILED)
                    failed += 1
                    if rules.get("on_error") == "stop":
                        _batch_pause_on_error(
                            runner,
                            db,
                            batch_id,
                            done=done,
                            failed=failed,
                            skipped=skipped,
                        )
                        return
                    continue

                current = db.get_job(job_id) or {}
                if current.get("status") == JobStatus.CANCELLED.value:
                    continue
                if current.get("status") != JobStatus.COMPLETED.value:
                    failed += 1
                    if rules.get("on_error") == "stop":
                        _batch_pause_on_error(
                            runner,
                            db,
                            batch_id,
                            done=done,
                            failed=failed,
                            skipped=skipped,
                        )
                        return
                    continue

                if rules.get("speakers"):
                    if is_cloud_only():
                        logger.info(
                            "skip batch speakers for job %s (cloud_only mode)",
                            job_id,
                        )
                    else:
                        try:
                            module = importlib.import_module("slysh.speakers_msdd")
                            assign_speakers(db, job_id, module.MsddSpeakersBackend())
                        except Exception as exc:
                            logging.exception("batch speakers failed for job %s", job_id)
                            db.set_error(job_id, str(exc))

                if rules.get("export"):
                    try:
                        _export_batch_job(
                            db,
                            job_id,
                            job,
                            rules,
                            used_names=export_used,
                        )
                    except Exception as exc:
                        logging.exception("batch export failed for job %s", job_id)
                        db.set_error(job_id, str(exc))

                done += 1

                with runner.lock:
                    if runner.pause_after_current:
                        db.update_batch(batch_id, status=BatchStatus.PAUSED)
                        runner.summary = {
                            "done": done,
                            "failed": failed,
                            "skipped": skipped,
                            "paused": True,
                        }
                        return
        finally:
            with runner.lock:
                runner.current_job_id = None
                active_batch = runner.batch_id
                runner.batch_id = None
                runner.pause_after_current = False
                runner.cancel_requested = False
            if active_batch == batch_id:
                batch = db.get_batch(batch_id)
                if batch and batch.get("status") == BatchStatus.RUNNING.value:
                    if failed > 0 and done > 0:
                        db.update_batch(
                            batch_id, status=BatchStatus.COMPLETED_WITH_ERRORS
                        )
                    elif failed > 0:
                        db.update_batch(batch_id, status=BatchStatus.PAUSED)
                    else:
                        db.update_batch(batch_id, status=BatchStatus.COMPLETED)
                if runner.summary is None:
                    runner.summary = {
                        "done": done,
                        "failed": failed,
                        "skipped": skipped,
                        "paused": False,
                    }

    thread = threading.Thread(target=work, daemon=True)
    runner.thread = thread
    thread.start()


def pause_batch(app: FastAPI, batch_id: int) -> bool:
    runner = get_runner(app)
    with runner.lock:
        if runner.batch_id != batch_id:
            return False
        runner.pause_after_current = True
    return True


def cancel_batch(
    app: FastAPI,
    db: Database,
    batch_id: int,
    *,
    engine_url: str | None,
    engine_cancel_fn: Callable[[str], None],
) -> bool:
    runner = get_runner(app)
    with runner.lock:
        if runner.batch_id != batch_id:
            return False
        runner.cancel_requested = True
        current_job_id = runner.current_job_id
    if current_job_id is not None:
        job = db.get_job(current_job_id) or {}
        if job.get("status") == JobStatus.RUNNING.value:
            if str(job.get("kind") or "") == JobKind.YOUTUBE.value:
                cancel = getattr(app.state, "youtube_cancels", {}).get(current_job_id)
                if cancel is not None:
                    cancel.set()
            elif engine_url:
                try:
                    engine_cancel_fn(engine_url)
                except Exception:
                    logger.exception("engine cancel failed for batch job %s", current_job_id)
        db.set_status(int(current_job_id), JobStatus.CANCELLED)
    for job in db.list_batch_jobs(batch_id):
        if job["status"] in (JobStatus.IDLE.value, JobStatus.QUEUED.value):
            db.set_status(int(job["id"]), JobStatus.CANCELLED)
    db.update_batch(batch_id, status=BatchStatus.IDLE)
    return True
