from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from slysh.batch_import import scan_paths
from slysh.batch_rules import is_youtube_batch_rules, normalize_rules
from slysh.catalog import GIGAAM_ID, get_model, is_downloadable_local_id, list_asr_models
from slysh.compute import (
    apply_preference,
    compute_payload,
    is_cloud_only,
    load_engine_mode,
    load_asr_id,
    load_asr_local_id,
    load_asr_remote_id,
    load_preference,
    save_asr_id,
    save_preference,
    write_asr_env,
    write_env,
)
from slysh.batch_runner import (
    cancel_batch,
    get_runner,
    is_batch_active,
    pause_batch,
    start_batch,
)
from slysh.chunking import SAMPLE_RATE, offset_segments, slice_pcm_range
from slysh.asr_coordinator import (
    AsrCoordinator,
    job_run_active,
    job_run_id,
    pump_local_queued,
    pump_remote_queued,
)
from slysh.cuda_fallback import format_job_asr_error
from slysh.decode import decode_pcm_16k_mono
from slysh.db import Database, SegmentsRevisionConflictError
from slysh.engine_client import cancel as engine_cancel
from slysh.engine_client import health as engine_health
from slysh.engine_client import transcribe_chunk
from slysh.transcribe import transcribe_pcm_chunks
from slysh.export import (
    suggested_export_path,
    unique_export_path,
    write_job_export,
    youtube_export_meta_from_job,
)
from slysh.live_buffer import LiveSession
from slysh.job_time import job_duration_s
from slysh.meeting_capture import (
    NO_OUTPUT_HINT,
    NOT_WINDOWS_HINT,
    MeetingCapture,
    MeetingCaptureError,
    list_input_devices,
    list_output_devices,
    loopback_supported,
    open_mic_input_stream,
    refresh_audio_devices,
    resample_to_16k,
)
from slysh.models import BatchStatus, JobKind, JobStatus, Segment
from slysh.open_paths import open_file, resolve_existing, reveal_in_folder
from slysh.paths import (
    catalog_roots,
    gigaam_download_root,
    model_root,
    project_models_dir,
    recordings_dir,
    web_dir,
)
from slysh.providers import (
    REMOTE_BACKENDS,
    delete_custom_provider,
    get_custom_provider,
    get_http_preset,
    gemini_status,
    public_apify,
    public_providers,
    save_apify,
    save_http_preset,
    save_openrouter,
    upsert_custom_provider,
)
from slysh.http_proxy import public_proxy_config, save_proxy_config
from slysh.remote_asr import (
    RemoteAsrError,
    fetch_openrouter_stt_models,
    transcribe_http_file,
    transcribe_media,
)
from slysh.model_download import model_download_payload, start_model_download
from slysh.runtime_setup import (
    activate_cloud_only_mode,
    dismiss_engine_setup,
    dismiss_model_setup,
    enable_local_engine_mode,
    engine_packages_ok,
    setup_status,
    start_engine_install,
)
from slysh.subprocess_win import subprocess_no_console_kwargs, terminate_process_tree
from slysh.updates import (
    app_info,
    apply_update,
    check_for_updates,
    download_status,
    schedule_process_exit,
    start_download,
    updates_enabled,
)

CLOUD_ONLY_ENGINE_MSG = (
    "Включён режим «только облако». Выберите провайдера в настройках или отключите этот режим."
)
from slysh.speakers import SPEAKER_CANCELLED_MESSAGE, SpeakerCancelledError, assign_speakers
from slysh.source_path import require_existing_file
from slysh.time_range import normalize_range
from slysh.transcript import format_transcript, parse_transcript
from slysh.ui_locale import resolve_ui_locale, save_ui_locale
from slysh.youtube_cookies import (
    YoutubeCookiesError,
    cookies_status,
    extract_cookies,
    import_cookies_file,
    list_browser_profiles,
)
from slysh.youtube_ingest import (
    YoutubeIngestError,
    attach_youtube_video,
    delete_job_ingest_meta,
    load_job_ingest_meta,
    load_job_youtube_video,
    normalize_youtube_url,
    save_job_ingest_meta,
    youtube_status,
    youtube_video_meta,
)
from slysh.youtube_channel import (
    YoutubeChannelError,
    YoutubeFeedFilters,
    expand_youtube_sources,
)

_MODEL_SUFFIXES = {".ckpt", ".pt", ".pth", ".onnx"}


class CreateJobBody(BaseModel):
    path: str
    batch_id: int | None = None


class BatchCreateBody(BaseModel):
    name: str | None = None
    rules: dict | None = None


class BatchPatchBody(BaseModel):
    name: str | None = None
    rules: dict | None = None
    archived: bool | None = None


class JobPatchBody(BaseModel):
    archived: bool | None = None


class BatchItemsBody(BaseModel):
    paths: list[str]
    recursive: bool = False


class BatchScanBody(BaseModel):
    paths: list[str]
    recursive: bool = False


class BatchReorderBody(BaseModel):
    job_ids: list[int]


class SegmentBody(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None


class PatchSegmentsBody(BaseModel):
    segments: list[SegmentBody] | None = None
    transcript: str | None = None
    expected_revision: int | None = None


class ExportBody(BaseModel):
    fmt: str
    path: str | None = None


class BatchExportBody(BaseModel):
    fmt: str
    directory: str


class JobsExportBody(BaseModel):
    fmt: str
    directory: str
    job_ids: list[int]


class OpenPathBody(BaseModel):
    path: str
    reveal: bool = False


class ExportPathsBody(BaseModel):
    paths: list[str]


class LiveStartBody(BaseModel):
    device_id: int | None = None


class MeetingStartBody(BaseModel):
    output_device_id: int | str | None = None
    mic_device_id: int | None = None
    include_mic: bool = True


class ComputeBody(BaseModel):
    preference: str


class UiLocaleBody(BaseModel):
    ui_locale: str


class AsrModelBody(BaseModel):
    id: str


class ModelDownloadBody(BaseModel):
    id: str | None = None


class EngineSetupBody(BaseModel):
    mark_pending_model: bool = False


class OpenRouterBody(BaseModel):
    api_key: str | None = None
    model: str | None = None


class ProxyBody(BaseModel):
    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    targets: dict[str, bool] | None = None


class CustomProviderBody(BaseModel):
    id: str | None = None
    name: str
    endpoint: str = ""
    model: str = ""
    protocol: str = "openai"
    api_key: str | None = None


class HttpPresetBody(BaseModel):
    api_key: str | None = None
    model: str | None = None


class JobTranscribeBody(BaseModel):
    start_ms: int | None = None
    end_ms: int | None = None


class ApifyBody(BaseModel):
    api_key: str | None = None


class YoutubeIngestBody(BaseModel):
    url: str
    method: str = "apify"
    language: str = "ru"


class YoutubeCookiesExtractBody(BaseModel):
    browser: str
    profile: str


class YoutubeCookiesImportBody(BaseModel):
    path: str


class YoutubeBatchFiltersBody(BaseModel):
    limit: int | None = None
    date: str | None = None
    dateafter: str | None = None
    datebefore: str | None = None
    start_video: str | None = None
    direction: str = "older"


class YoutubeBatchResolveBody(BaseModel):
    mode: str = "lines"
    lines: str | None = None
    feed_url: str | None = None
    filters: YoutubeBatchFiltersBody | None = None


class YoutubeBatchCreateBody(BaseModel):
    name: str | None = None
    mode: str = "lines"
    lines: str | None = None
    feed_url: str | None = None
    filters: YoutubeBatchFiltersBody | None = None
    method: str = "apify"
    language: str = "ru"
    rules: dict | None = None
    autostart: bool = True


class LibraryCheckExistingBody(BaseModel):
    files: list[str] | None = None
    youtube_urls: list[str] | None = None


NO_MIC_HINT = "Микрофон не найден. Проверьте устройства записи Windows."
LIVE_CLI_HINT = "Диктофон не работает через Gemini CLI. Выберите локальную или HTTP-модель."
MEETING_CLI_HINT = (
    "Запись встречи не работает через Gemini CLI. Выберите локальную или HTTP-модель."
)
LIVE_BUSY_HINT = "Сначала остановите диктофон."
MEETING_BUSY_HINT = "Сначала остановите запись встречи."
MEETING_ALREADY_HINT = "Запись встречи уже идёт."
MEETING_NOT_ACTIVE_HINT = "Запись встречи не запущена."
MEETING_ALREADY_PAUSED_HINT = "Запись встречи уже на паузе."
MEETING_NOT_PAUSED_HINT = "Запись встречи не на паузе."
LIVE_NOT_ACTIVE_HINT = "Диктофон не запущен."
LIVE_ALREADY_PAUSED_HINT = "Диктофон уже на паузе."
LIVE_NOT_PAUSED_HINT = "Диктофон не на паузе."
LIVE_ALREADY_HINT = "Диктофон уже записывает."


def _parse_last_export_paths(job: dict) -> list[str]:
    raw = job.get("last_export_paths")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if str(p).strip()]
        except json.JSONDecodeError:
            pass
    single = job.get("last_export_path")
    if single:
        text = str(single).strip()
        if text:
            return [text]
    return []


def _job_payload(job: dict) -> dict:
    payload = dict(job)
    payload["last_export_paths"] = _parse_last_export_paths(job)
    return payload


def _apply_transcribe_range(db: Database, job_id: int, body: JobTranscribeBody) -> None:
    if "start_ms" not in body.model_fields_set and "end_ms" not in body.model_fields_set:
        return
    try:
        start, end = normalize_range(body.start_ms, body.end_ms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.set_job_range(job_id, start, end)


def _decorate_batch(app: FastAPI, batch: dict, jobs: list[dict]) -> dict:
    decorated_jobs = [_decorate_job(app, _job_payload(job)) for job in jobs]
    total = len(decorated_jobs)
    done = sum(1 for j in decorated_jobs if j["status"] == JobStatus.COMPLETED.value)
    failed = sum(1 for j in decorated_jobs if j["status"] == JobStatus.FAILED.value)
    active = sum(
        1
        for j in decorated_jobs
        if j["status"] in (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
    )
    payload = {
        "id": batch["id"],
        "name": batch["name"],
        "status": batch["status"],
        "rules": batch.get("rules") or normalize_rules(None),
        "batch_type": (batch.get("rules") or normalize_rules(None)).get("batch_type", "file"),
        "created_at": batch.get("created_at"),
        "jobs": decorated_jobs,
        "done_count": done,
        "failed_count": failed,
        "active_count": active,
        "total_count": total,
        "running": is_batch_active(app, int(batch["id"])),
    }
    runner = get_runner(app)
    if runner.summary and runner.batch_id == batch["id"]:
        payload["summary"] = runner.summary
    return payload


def _require_batch(db: Database, batch_id: int) -> dict:
    batch = db.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return batch


def _batch_job_kind_mismatch(batch: dict, jobs: list[dict]) -> str | None:
    rules = normalize_rules(batch.get("rules"))
    youtube_batch = is_youtube_batch_rules(rules)
    for job in jobs:
        is_yt = str(job.get("kind") or "") == JobKind.YOUTUBE.value
        if youtube_batch and not is_yt:
            return "В YouTube-пакете не должно быть файловых заданий."
        if not youtube_batch and is_yt:
            return "YouTube-задания можно добавлять только в YouTube-пакет."
    return None


def _filters_from_body(raw: YoutubeBatchFiltersBody | None) -> YoutubeFeedFilters:
    if raw is None:
        return YoutubeFeedFilters()
    direction = str(raw.direction or "older").strip().lower()
    if direction not in {"older", "newer"}:
        direction = "older"
    return YoutubeFeedFilters(
        limit=raw.limit,
        date=(raw.date or "").strip() or None,
        dateafter=(raw.dateafter or "").strip() or None,
        datebefore=(raw.datebefore or "").strip() or None,
        start_video=(raw.start_video or "").strip() or None,
        direction=direction,  # type: ignore[arg-type]
    )


def _resolve_youtube_videos(body: YoutubeBatchResolveBody) -> list[dict]:
    mode = str(body.mode or "lines").strip().lower()
    if mode not in {"lines", "feed"}:
        raise HTTPException(status_code=400, detail="mode должен быть lines или feed.")
    try:
        refs = expand_youtube_sources(
            mode=mode,  # type: ignore[arg-type]
            lines=body.lines,
            feed_url=body.feed_url,
            filters=_filters_from_body(body.filters),
        )
    except YoutubeChannelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        {"video_id": ref.video_id, "url": ref.url, "title": ref.title}
        for ref in refs
    ]


def _attach_youtube_existing_jobs(db: Database, videos: list[dict]) -> list[dict]:
    video_ids = [str(v.get("video_id") or "") for v in videos if v.get("video_id")]
    matches = db.find_existing_transcripts(youtube_video_ids=video_ids)
    by_video_id = {
        str(m["video_id"]): m for m in matches if m.get("video_id")
    }
    enriched: list[dict] = []
    for item in videos:
        payload = dict(item)
        match = by_video_id.get(str(item.get("video_id") or ""))
        if match:
            payload["existing_job"] = {
                "id": match["job_id"],
                "source_title": match.get("source_title") or "",
            }
        else:
            payload["existing_job"] = None
        enriched.append(payload)
    return enriched


def _library_check_existing_payload(
    db: Database,
    body: LibraryCheckExistingBody,
) -> dict:
    file_paths: list[str] = []
    for raw in body.files or []:
        try:
            source = require_existing_file(raw)
            file_paths.append(str(source.resolve()))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    video_ids: list[str] = []
    seen_video: set[str] = set()
    for raw in body.youtube_urls or []:
        try:
            _url, video_id = normalize_youtube_url(raw)
        except YoutubeIngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if video_id in seen_video:
            continue
        seen_video.add(video_id)
        video_ids.append(video_id)

    matches = db.find_existing_transcripts(
        file_paths=file_paths,
        youtube_video_ids=video_ids,
    )
    return {"matches": matches, "count": len(matches)}


def _youtube_batch_rules(
    body: YoutubeBatchCreateBody,
    method: str,
    language: str,
) -> dict:
    rules = normalize_rules(body.rules)
    rules["batch_type"] = "youtube"
    rules["youtube_method"] = method
    rules["youtube_language"] = language
    rules["speakers"] = False
    return rules


def _create_youtube_batch(app: FastAPI, db: Database, body: YoutubeBatchCreateBody) -> dict:
    method = str(body.method or "apify").strip().lower()
    if method not in {"apify", "ytdlp"}:
        raise HTTPException(status_code=400, detail="Способ должен быть apify или ytdlp.")
    language = str(body.language or "ru").strip() or "ru"
    resolve_body = YoutubeBatchResolveBody(
        mode=body.mode,
        lines=body.lines,
        feed_url=body.feed_url,
        filters=body.filters,
    )
    videos = _resolve_youtube_videos(resolve_body)
    if not videos:
        raise HTTPException(status_code=400, detail="Список видео пуст.")
    name = (body.name or "").strip()
    if not name:
        name = f"YouTube · {datetime.now().strftime('%d.%m %H:%M')}"
    rules = _youtube_batch_rules(body, method, language)
    batch_id = db.create_batch(name, rules)
    urls = [item["url"] for item in videos]
    job_ids = db.add_youtube_jobs_to_batch(batch_id, urls)
    for job_id, item in zip(job_ids, videos, strict=True):
        title = str(item.get("title") or "").strip()
        if title and not title.startswith("YouTube "):
            db.set_job_source_title(job_id, title)
    if body.autostart:
        if is_batch_active(app):
            raise HTTPException(
                status_code=400,
                detail="Пакет создан, но уже выполняется другой пакет.",
            )
        start_batch(
            app,
            db,
            batch_id,
            run_file_job=_run_file_asr_job,
            ensure_engine=_ensure_engine_url,
            run_engine_job=_run_engine_job,
            engine_cancel=engine_cancel,
        )
    batch = _require_batch(db, batch_id)
    return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))


def _ensure_engine_url(app: FastAPI) -> str:
    if is_cloud_only():
        raise HTTPException(status_code=400, detail=CLOUD_ONLY_ENGINE_MSG)
    skip = os.environ.get("GIGAAM_SKIP_ENGINE") == "1"
    auto_start = bool(getattr(app.state, "auto_start_engine", False))
    with app.state.engine_lock:
        if _engine_needs_start(app):
            if skip or not auto_start:
                raise HTTPException(status_code=400, detail="Движок не запущен.")
            app.state.engine_starting = True
            try:
                _spawn_engine(app)
            finally:
                app.state.engine_starting = False
    url = getattr(app.state, "engine_url", None)
    if not url:
        raise HTTPException(status_code=500, detail="engine unavailable")
    return url


def _decorate_job(
    app: FastAPI,
    job: dict,
    segments: list | None = None,
    *,
    enrich_youtube: bool = False,
) -> dict:
    payload = dict(job)
    running = getattr(app.state, "speaker_jobs", {})
    errors = getattr(app.state, "speaker_errors", {})
    started = getattr(app.state, "speaker_started", {})
    payload["speakers_running"] = running.get(job["id"]) == "running"
    payload["engine_starting"] = bool(getattr(app.state, "engine_starting", False))
    started_at = started.get(job["id"])
    if payload["speakers_running"] and started_at:
        payload["speakers_elapsed_s"] = round(time.monotonic() - started_at, 1)
    error = errors.get(job["id"])
    if error:
        payload["speakers_error"] = error
    duration = job_duration_s(payload)
    if duration is not None:
        payload["duration_s"] = round(duration, 1)
    attach_youtube_video(payload, segments, enrich=enrich_youtube)
    return payload


def _display_segments(
    db: Database,
    job_id: int,
    segments: list[Segment],
) -> list[Segment]:
    names = db.list_speaker_names(job_id)
    if not names:
        return segments
    return [
        Segment(
            s.start_ms,
            s.end_ms,
            s.text,
            speaker=names.get(s.speaker, s.speaker) if s.speaker else None,
        )
        for s in segments
    ]


def _segments_payload(
    segments: list[Segment],
    speaker_names: dict[str, str] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    for s in segments:
        key = s.speaker
        display = key
        if key and speaker_names:
            display = speaker_names.get(key, key)
        rows.append(
            {
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text": s.text,
                "speaker": display,
                "speaker_key": key,
            }
        )
    return rows


def _require_job(db: Database, job_id: int) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _write_job_export_file(db: Database, job: dict, out: Path, fmt: str) -> None:
    job_id = int(job["id"])
    segments = _display_segments(db, job_id, db.list_segments(job_id))
    if _is_youtube_job(job):
        video = load_job_youtube_video(job_id) or {}
        _, language = load_job_ingest_meta(job_id)
        meta = youtube_export_meta_from_job(job, video, language)
        write_job_export(out, segments, fmt, youtube_meta=meta)
    else:
        write_job_export(out, segments, fmt, job=job)


def _export_jobs_to_directory(db: Database, jobs: list[dict], fmt: str, directory: str) -> dict:
    raw = (directory or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Укажите папку.")
    dest = Path(raw)
    if dest.exists() and not dest.is_dir():
        raise HTTPException(status_code=400, detail="Укажите папку, а не файл.")
    completed = [job for job in jobs if job.get("status") == JobStatus.COMPLETED.value]
    if not completed:
        raise HTTPException(status_code=400, detail="Нет готовых расшифровок для экспорта.")
    used: set[str] = set()
    paths: list[str] = []
    try:
        for job in completed:
            stem = Path(str(job.get("source_path") or "")).stem or "transcript"
            out = unique_export_path(dest, stem, fmt, used)
            _write_job_export_file(db, job, out, fmt)
            db.set_last_export_path(int(job["id"]), str(out))
            paths.append(str(out))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось сохранить файл: {exc}") from exc
    return {
        "directory": str(dest),
        "exported": len(paths),
        "skipped": len(jobs) - len(completed),
        "paths": paths,
    }


def _selected_model():
    selected = load_asr_id()
    item = get_model(selected)
    if item is not None:
        return item
    items = list_asr_models()
    for candidate in items:
        if candidate.id == GIGAAM_ID:
            return candidate
    return items[0] if items else None


def model_is_ready() -> bool:
    item = _selected_model()
    if item is not None:
        return bool(item.ready)
    download = gigaam_download_root()
    for path in download.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in _MODEL_SUFFIXES:
            return True
        return True
    root = model_root()
    if root.resolve() != download.resolve():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in _MODEL_SUFFIXES:
                return True
    return False


def _model_status() -> str:
    return "ready" if model_is_ready() else "missing"


ENGINE_START_PORT_WAIT_S = 60.0


def _selected_asr_preflight_error() -> str | None:
    """Human-readable reason when the current ASR choice cannot run."""
    selected = _selected_model()
    if selected is None:
        return "Модель распознавания не выбрана. Укажите её в Настройках."
    if selected.backend in REMOTE_BACKENDS:
        if not selected.ready:
            hint = (selected.hint or "").strip()
            return hint or f"Настройте доступ к модели «{selected.label}» в Настройках."
        return None
    if is_cloud_only():
        return CLOUD_ONLY_ENGINE_MSG
    if not selected.ready:
        if selected.downloadable:
            return (
                f"Модель «{selected.label}» не скачана. "
                "Загрузите её в Настройках → ASR."
            )
        return (
            f"Модель «{selected.label}» недоступна. "
            "Проверьте файлы в каталоге models/."
        )
    if not engine_packages_ok():
        return (
            "Сначала установите локальные пакеты расшифровки "
            "(torch и движки) в Настройках."
        )
    return None


def _require_asr_ready() -> None:
    message = _selected_asr_preflight_error()
    if message:
        raise HTTPException(status_code=400, detail=message)


def _engine_spawn_failure_detail(proc: subprocess.Popen, lines: list[str]) -> str:
    tail = "\n".join(lines[-10:]).strip()
    lower = tail.lower()
    if "not available" in lower or "install engine" in lower:
        return tail[:500]
    if "gigaam" in lower and "not" in lower:
        return tail[:500] if tail else "GigaAM недоступен. Установите пакеты движка в Настройках."
    code = proc.poll()
    if code not in (None, 0):
        if tail:
            return f"Движок завершился с кодом {code}: {tail[:400]}"
        return f"Движок завершился с кодом {code}. Проверьте логи и установку torch/GigaAM."
    if tail:
        return (
            "Движок не сообщил порт запуска. "
            f"Последние строки: {tail[:400]}"
        )
    return (
        "Движок не запустился. Проверьте, что модель скачана, "
        "пакеты torch/GigaAM установлены, и повторите попытку."
    )


def _engine_status(app: FastAPI) -> str:
    url = getattr(app.state, "engine_url", None)
    if not url:
        return "down"
    try:
        info = engine_health(url)
        device = str(info.get("device", "cpu")).lower()
        if "cuda" in device or device == "gpu":
            return "gpu"
        return "cpu"
    except Exception:
        return "down"


def _existing_engine_port(app: FastAPI) -> int | None:
    url = getattr(app.state, "engine_url", None)
    if not url:
        return None
    try:
        return int(str(url).rsplit(":", 1)[-1].rstrip("/"))
    except ValueError:
        return None


def _drain_engine_output(stream) -> None:
    try:
        for line in stream:
            text = line.rstrip()
            if text:
                logging.info("engine: %s", text)
    except Exception:
        logging.debug("engine stdout closed", exc_info=True)


def _spawn_engine(app: FastAPI) -> dict[str, int]:
    if is_cloud_only():
        raise HTTPException(status_code=400, detail=CLOUD_ONLY_ENGINE_MSG)
    selected = _selected_model()
    if selected is not None and selected.backend in REMOTE_BACKENDS:
        raise HTTPException(
            status_code=500,
            detail="Локальный движок не используется для облачной модели.",
        )
    preflight = _selected_asr_preflight_error()
    if preflight:
        raise HTTPException(status_code=400, detail=preflight)
    if _engine_status(app) != "down":
        existing = _existing_engine_port(app)
        if existing is not None:
            return {"port": existing}

    cmd = [sys.executable, "-m", "slysh.engine_server"]
    if os.environ.get("GIGAAM_ENGINE_FAKE") == "1":
        cmd.append("--fake")

    env = os.environ.copy()
    write_env(env, load_preference())
    selected = _selected_model()
    write_asr_env(
        env,
        selected.id if selected else load_asr_id(),
        selected.path if selected else None,
    )
    env.setdefault("GIGAAM_MODEL_ROOT", str(model_root()))
    from slysh.decode import find_ffmpeg

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        env["FFMPEG_BINARY"] = ffmpeg
        env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
        **subprocess_no_console_kwargs(),
    )
    port: int | None = None
    stdout = proc.stdout
    boot_lines: list[str] = []
    if stdout is not None:
        port_box: list[int | None] = [None]
        boot_lock = threading.Lock()

        def _read_stdout() -> None:
            try:
                for line in stdout:
                    text = line.rstrip()
                    if port_box[0] is None:
                        if text:
                            with boot_lock:
                                boot_lines.append(text)
                            logging.info("engine: %s", text)
                        if line.startswith("PORT="):
                            port_box[0] = int(line.strip().split("=", 1)[1])
                    elif text:
                        logging.info("engine: %s", text)
            except Exception:
                logging.debug("engine stdout closed", exc_info=True)

        threading.Thread(target=_read_stdout, daemon=True).start()
        deadline = time.monotonic() + ENGINE_START_PORT_WAIT_S
        while time.monotonic() < deadline:
            if port_box[0] is not None:
                port = port_box[0]
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        if port is None:
            if proc.poll() is None:
                terminate_process_tree(proc, timeout=5)
            detail = _engine_spawn_failure_detail(proc, boot_lines)
            raise HTTPException(status_code=500, detail=detail)

    app.state.engine_proc = proc
    app.state.engine_url = f"http://127.0.0.1:{port}"
    return {"port": port}


def _stop_engine(app: FastAPI) -> None:
    proc = getattr(app.state, "engine_proc", None)
    if proc is not None and proc.poll() is None:
        try:
            terminate_process_tree(proc, timeout=8)
        except Exception:
            logging.debug("engine terminate failed", exc_info=True)
    app.state.engine_proc = None
    app.state.engine_url = None
    app.state.engine_starting = False


def _pipeline_busy(app: FastAPI, db: Database) -> bool:
    if is_batch_active(app):
        return True
    if getattr(app.state, "engine_starting", False):
        return True
    if getattr(app.state, "speaker_jobs", {}):
        return True
    for job in db.list_jobs():
        if job["status"] in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
            return True
    return False


_ACTIVE_ENGINE_PHASES = frozenset({"starting", "decode", "asr"})


def engine_progress_fraction(info: dict) -> float | None:
    """Live engine progress, or None if the value is leftover from a previous job."""
    phase = str(info.get("phase") or "")
    if phase not in _ACTIVE_ENGINE_PHASES:
        return None
    try:
        value = float(info.get("progress") or 0)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))


def _segments_from_engine(payload: dict) -> list[Segment]:
    return [
        Segment(
            start_ms=int(item["start_ms"]),
            end_ms=int(item["end_ms"]),
            text=str(item["text"]),
            speaker=item.get("speaker"),
        )
        for item in payload.get("segments", [])
    ]


def _engine_job_cancelled(db: Database, job_id: int) -> bool:
    current = db.get_job(job_id) or {}
    return current.get("status") == JobStatus.CANCELLED.value


def _run_engine_job(db: Database, engine_url: str, job_id: int, source_path: str) -> None:
    job = db.get_job(job_id) or {}
    run_id = job_run_id(db, job_id)
    if not job_run_active(db, job_id, run_id):
        return
    db.set_status(job_id, JobStatus.RUNNING)
    db.set_progress(job_id, 0)
    db.replace_segments(job_id, [])
    try:
        job = db.get_job(job_id) or {}
        run_id = job_run_id(db, job_id)
        if not job_run_active(db, job_id, run_id):
            return
        pcm, _sr = decode_pcm_16k_mono(source_path)
        pcm, offset_ms = slice_pcm_range(
            pcm, job.get("range_start_ms"), job.get("range_end_ms")
        )
        db.set_progress(job_id, 0.01)

        def transcribe_chunk_fn(chunk_pcm):
            payload = transcribe_chunk(
                engine_url,
                np.asarray(chunk_pcm, dtype=np.float32).tolist(),
            )
            return _segments_from_engine(payload)

        def on_segments(piece: list[Segment]) -> None:
            if not job_run_active(db, job_id, run_id):
                return
            db.append_segments(job_id, piece)

        def on_progress(value: float) -> None:
            if not job_run_active(db, job_id, run_id):
                return
            db.set_progress(job_id, 0.01 + 0.99 * float(value))

        status, _segs = transcribe_pcm_chunks(
            pcm,
            transcribe_chunk_fn=transcribe_chunk_fn,
            cancelled=lambda: not job_run_active(db, job_id, run_id)
            or _engine_job_cancelled(db, job_id),
            on_progress=on_progress,
            on_segments=on_segments,
            start_ms_offset=int(offset_ms or 0),
        )
        if not job_run_active(db, job_id, run_id):
            return
        if status == "cancelled" or _engine_job_cancelled(db, job_id):
            if not _engine_job_cancelled(db, job_id):
                db.set_status(job_id, JobStatus.CANCELLED)
            return
        db.set_progress(job_id, 1)
        db.set_status(job_id, JobStatus.COMPLETED)
    except Exception as exc:
        if not job_run_active(db, job_id, run_id) or _engine_job_cancelled(db, job_id):
            return
        logging.exception("engine job %s failed", job_id)
        db.set_error(job_id, format_job_asr_error(exc))
        db.set_status(job_id, JobStatus.FAILED)


def _engine_needs_start(app: FastAPI) -> bool:
    url = getattr(app.state, "engine_url", None)
    if not url:
        return True
    return _engine_status(app) == "down"


def _pump_asr_queues(app: FastAPI, db: Database) -> None:
    pump_local_queued(
        app,
        db,
        is_youtube_job=_is_youtube_job,
        is_remote_model=lambda: (
            _selected_model() is not None
            and _selected_model().backend in REMOTE_BACKENDS
        ),
        start_engine_job=_start_engine_job,
    )
    pump_remote_queued(
        app,
        db,
        is_youtube_job=_is_youtube_job,
        is_remote_model=lambda: (
            _selected_model() is not None
            and _selected_model().backend in REMOTE_BACKENDS
        ),
        start_remote_job=_schedule_remote_job,
    )


def _start_engine_job(app: FastAPI, db: Database, job_id: int, source_path: str) -> None:
    skip = os.environ.get("GIGAAM_SKIP_ENGINE") == "1"
    auto_start = bool(getattr(app.state, "auto_start_engine", False))

    def boot() -> None:
        coord: AsrCoordinator = app.state.asr_coordinator
        if not coord.try_begin_local(job_id):
            return
        try:
            if is_cloud_only():
                db.set_error(job_id, CLOUD_ONLY_ENGINE_MSG)
                db.set_status(job_id, JobStatus.FAILED)
                return
            with app.state.engine_lock:
                if _engine_needs_start(app):
                    if skip or not auto_start:
                        db.set_error(
                            job_id,
                            "Движок не запущен. Установите пакеты расшифровки или выберите облачный провайдер.",
                        )
                        db.set_status(job_id, JobStatus.FAILED)
                        return
                    app.state.engine_starting = True
                    try:
                        _spawn_engine(app)
                    except HTTPException as exc:
                        db.set_error(job_id, str(exc.detail))
                        db.set_status(job_id, JobStatus.FAILED)
                        return
                    finally:
                        app.state.engine_starting = False
            url = getattr(app.state, "engine_url", None)
            if not url:
                db.set_error(
                    job_id,
                    "Движок не запущен. Установите пакеты расшифровки или выберите облачный провайдер.",
                )
                db.set_status(job_id, JobStatus.FAILED)
                return
            _run_engine_job(db, url, job_id, source_path)
        except Exception as exc:
            logging.exception("engine job %s failed to start", job_id)
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
        finally:
            coord.end_local(job_id)
            _pump_asr_queues(app, db)

    threading.Thread(target=boot, daemon=True).start()


def _schedule_remote_job(app: FastAPI, db: Database, job_id: int, source_path: str) -> None:
    def boot() -> None:
        coord: AsrCoordinator = app.state.asr_coordinator
        if not coord.try_begin_remote(job_id):
            return
        try:
            _run_remote_job(app, db, job_id, source_path)
        except Exception as exc:
            logging.exception("remote job %s failed", job_id)
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
        finally:
            coord.end_remote(job_id)
            _pump_asr_queues(app, db)

    threading.Thread(target=boot, daemon=True).start()


def _run_file_asr_job(
    app: FastAPI, db: Database, job_id: int, source_path: str
) -> None:
    selected = _selected_model()
    if selected is not None and selected.backend in REMOTE_BACKENDS:
        coord: AsrCoordinator = app.state.asr_coordinator
        if not coord.begin_remote_wait(job_id):
            db.set_error(job_id, "Не удалось дождаться облачного исполнителя.")
            db.set_status(job_id, JobStatus.FAILED)
            return
        try:
            _run_remote_job(app, db, job_id, source_path)
        finally:
            coord.end_remote(job_id)
            _pump_asr_queues(app, db)
        return
    coord = app.state.asr_coordinator
    if not coord.begin_local_wait(job_id):
        db.set_error(job_id, "Не удалось дождаться локального движка.")
        db.set_status(job_id, JobStatus.FAILED)
        return
    try:
        engine_url = _ensure_engine_url(app)
        _run_engine_job(db, engine_url, job_id, source_path)
    finally:
        coord.end_local(job_id)
        _pump_asr_queues(app, db)


def _run_remote_job(app: FastAPI, db: Database, job_id: int, source_path: str) -> None:
    job = db.get_job(job_id) or {}
    run_id = job_run_id(db, job_id)
    if not job_run_active(db, job_id, run_id):
        return
    db.set_status(job_id, JobStatus.RUNNING)
    db.set_progress(job_id, 0)
    db.replace_segments(job_id, [])
    selected = _selected_model()
    if selected is None or selected.backend not in REMOTE_BACKENDS:
        db.set_error(job_id, "Облачная модель не выбрана.")
        db.set_status(job_id, JobStatus.FAILED)
        return
    cancel_event = threading.Event()
    app.state.remote_cancels[job_id] = cancel_event
    try:
        job = db.get_job(job_id) or {}

        def on_segments(piece: list[Segment]) -> None:
            if not job_run_active(db, job_id, run_id):
                return
            db.append_segments(job_id, piece)

        def on_progress(value: float) -> None:
            if not job_run_active(db, job_id, run_id):
                return
            db.set_progress(job_id, 0.01 + 0.99 * float(value))

        transcribe_media(
            backend=selected.backend,
            model_id=selected.id,
            source_path=source_path,
            start_ms=job.get("range_start_ms"),
            end_ms=job.get("range_end_ms"),
            cancelled=lambda: cancel_event.is_set() or not job_run_active(db, job_id, run_id),
            on_progress=on_progress,
            on_segments=on_segments,
        )
        if not job_run_active(db, job_id, run_id):
            return
        current = db.get_job(job_id) or {}
        if current.get("status") == JobStatus.CANCELLED.value or cancel_event.is_set():
            if current.get("status") != JobStatus.CANCELLED.value:
                db.set_status(job_id, JobStatus.CANCELLED)
            return
        db.set_progress(job_id, 1)
        db.set_status(job_id, JobStatus.COMPLETED)
    except Exception as exc:
        if not job_run_active(db, job_id, run_id):
            return
        current = db.get_job(job_id) or {}
        if current.get("status") == JobStatus.CANCELLED.value:
            return
        logging.exception("remote job %s failed", job_id)
        db.set_error(job_id, str(exc))
        db.set_status(job_id, JobStatus.FAILED)
    finally:
        app.state.remote_cancels.pop(job_id, None)


def _start_asr_job(app: FastAPI, db: Database, job_id: int, source_path: str) -> None:
    selected = _selected_model()
    if selected is not None and selected.backend in REMOTE_BACKENDS:
        _schedule_remote_job(app, db, job_id, source_path)
        return
    _start_engine_job(app, db, job_id, source_path)


def _is_youtube_job(job: dict) -> bool:
    return str(job.get("kind") or "") == JobKind.YOUTUBE.value


def _run_youtube_job(
    app: FastAPI,
    db: Database,
    job_id: int,
    url: str,
    method: str,
    language: str,
) -> None:
    from slysh.youtube_ingest import run_youtube_job as execute_youtube_job

    cancel_event = threading.Event()
    app.state.youtube_cancels[job_id] = cancel_event
    try:
        execute_youtube_job(
            db,
            job_id,
            url,
            method,  # type: ignore[arg-type]
            language,
            cancel_event=cancel_event,
        )
    finally:
        app.state.youtube_cancels.pop(job_id, None)


def _start_youtube_job(
    app: FastAPI,
    db: Database,
    job_id: int,
    url: str,
    method: str | None = None,
    language: str | None = None,
) -> None:
    resolved_method, resolved_language = load_job_ingest_meta(job_id)
    if method:
        resolved_method = method
    if language:
        resolved_language = language
    save_job_ingest_meta(job_id, resolved_method, resolved_language)

    def boot() -> None:
        _run_youtube_job(
            app,
            db,
            job_id,
            url,
            resolved_method,
            resolved_language,
        )

    threading.Thread(target=boot, daemon=True).start()


def _transcription_blocks_editor_save(job: dict) -> bool:
    if job.get("status") != JobStatus.RUNNING.value:
        return False
    if job.get("speakers_running"):
        return True
    kind = str(job.get("kind") or "")
    return kind in {
        JobKind.FILE.value,
        JobKind.YOUTUBE.value,
        JobKind.LIVE.value,
        JobKind.MEETING.value,
    }


def _empty_live_state() -> dict:
    return {
        "listening": False,
        "paused": False,
        "session": None,
        "stream": None,
        "ingest": None,
        "thread": None,
        "stop_event": None,
        "job_id": None,
        "device_id": None,
        "rms": 0.0,
        "error": None,
        "chunk_start_seconds": 0,
        "paused_at": None,
        "total_paused_s": 0.0,
        "kind": "live",
    }


def _close_live_ingest(state: dict) -> None:
    from slysh.audio_ingest import AudioIngestQueue

    ingest = state.pop("ingest", None)
    if isinstance(ingest, AudioIngestQueue):
        ingest.close()


def _ensure_live_ingest(state: dict) -> None:
    if state.get("ingest") is not None:
        return
    from slysh.audio_ingest import AudioIngestQueue

    def on_pcm(pcm: np.ndarray) -> None:
        session = state.get("session")
        if session is None:
            return
        session.push(pcm)
        if len(pcm):
            state["rms"] = float(np.sqrt(np.mean(np.square(pcm))))

    state["ingest"] = AudioIngestQueue(on_pcm, name="live-ingest")


def _live_session_active(state: dict) -> bool:
    return state.get("session") is not None


def _live_mic_callback(app: FastAPI, capture_rate: int):
    def _on_audio(indata, frames, time_info, status) -> None:
        state = app.state.live
        if state.get("paused"):
            state["rms"] = 0.0
            return
        ingest = state.get("ingest")
        if ingest is None:
            return
        pcm = resample_to_16k(np.asarray(indata, dtype=np.float32).reshape(-1), capture_rate)
        ingest.push(pcm)

    return _on_audio


def _live_status_payload(app: FastAPI, db: Database, state: dict) -> dict:
    session = state.get("session")
    session_active = _live_session_active(state)
    paused = bool(state.get("paused"))
    capturing = session_active and not paused
    remaining = 0.0
    if capturing and session is not None:
        remaining = float(session.remaining_s())
    payload = {
        "listening": capturing,
        "paused": paused,
        "session_active": session_active,
        "remaining_s": remaining,
        "rms": float(state.get("rms") or 0.0) if capturing else 0.0,
        "job_id": state.get("job_id"),
    }
    job_id = state.get("job_id")
    if job_id is not None:
        jid = int(job_id)
        segs = db.list_segments(jid)
        payload["segments"] = _segments_payload(
            segs, speaker_names=db.list_speaker_names(jid)
        )
    if state.get("error"):
        payload["error"] = state["error"]
    return payload


def _empty_meeting_state() -> dict:
    return {
        "listening": False,
        "paused": False,
        "session": None,
        "capture": None,
        "thread": None,
        "stop_event": None,
        "job_id": None,
        "rms_mic": 0.0,
        "rms_system": 0.0,
        "error": None,
        "chunk_start_seconds": 0,
        "started_monotonic": None,
        "paused_at": None,
        "total_paused_s": 0.0,
        "include_mic": True,
        "kind": "meeting",
    }


def _meeting_session_active(state: dict) -> bool:
    return state.get("session") is not None


def _meeting_elapsed_s(state: dict) -> float:
    started = state.get("started_monotonic")
    if started is None:
        return 0.0
    now = time.monotonic()
    total_paused = float(state.get("total_paused_s") or 0.0)
    paused_at = state.get("paused_at")
    if paused_at is not None:
        total_paused += now - float(paused_at)
    return max(0.0, now - float(started) - total_paused)


def _meeting_status_payload(app: FastAPI, db: Database, state: dict) -> dict:
    session = state.get("session")
    session_active = _meeting_session_active(state)
    paused = bool(state.get("paused"))
    capturing = session_active and not paused
    remaining = 0.0
    if capturing and session is not None:
        remaining = float(session.remaining_s())
    payload = {
        "listening": capturing,
        "paused": paused,
        "session_active": session_active,
        "remaining_s": remaining,
        "elapsed_s": _meeting_elapsed_s(state) if session_active else 0.0,
        "rms_mic": float(state.get("rms_mic") or 0.0),
        "rms_system": float(state.get("rms_system") or 0.0),
        "job_id": state.get("job_id"),
        "include_mic": bool(state.get("include_mic", True)),
    }
    job_id = state.get("job_id")
    if job_id is not None:
        jid = int(job_id)
        segs = db.list_segments(jid)
        payload["segments"] = _segments_payload(
            segs, speaker_names=db.list_speaker_names(jid)
        )
    if state.get("error"):
        payload["error"] = state["error"]
    return payload


def _active_capture_state(app: FastAPI) -> dict:
    meeting = getattr(app.state, "meeting", None)
    if meeting is not None and meeting.get("session") is not None:
        return meeting
    return app.state.live


def _live_is_busy(app: FastAPI) -> bool:
    live = app.state.live
    return bool(live.get("listening") or live.get("session"))


def _meeting_is_busy(app: FastAPI) -> bool:
    meeting = getattr(app.state, "meeting", None) or {}
    return bool(meeting.get("listening") or meeting.get("session"))


_MIC_NAME_SKIP = ("disabled", "unavailable", "disconnected", "not plugged", "not present")
_MIC_CACHE_TTL_S = 8.0


def _mic_name_excluded(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in _MIC_NAME_SKIP)


def _mic_is_available(index: int) -> bool:
    from slysh.sounddevice_lazy import sd

    try:
        info = sd.query_devices(index)
        native = int(float(info.get("default_samplerate") or 16000))
    except Exception:
        native = 16000
    for samplerate in (native, 16000, 48000, 44100):
        try:
            with sd.InputStream(
                device=index,
                channels=1,
                samplerate=samplerate,
                blocksize=0,
                dtype="float32",
            ):
                pass
            return True
        except Exception:
            continue
    return False


def _list_input_mics(app: FastAPI | None = None, *, force: bool = False) -> list[dict]:
    now = time.monotonic()
    if app is not None and not force:
        cached = getattr(app.state, "mic_cache", None)
        if cached and now - cached["ts"] < _MIC_CACHE_TTL_S:
            return list(cached["items"])
    try:
        out = list_input_devices(probe=_mic_is_available)
        if app is not None:
            app.state.mic_cache = {"ts": now, "items": out}
        return out
    except Exception:
        return []


def _ensure_engine_for_live(app: FastAPI) -> str | None:
    state = _active_capture_state(app)
    if not _engine_needs_start(app):
        return getattr(app.state, "engine_url", None)
    skip = os.environ.get("GIGAAM_SKIP_ENGINE") == "1"
    if skip or not getattr(app.state, "auto_start_engine", False):
        return None
    try:
        _spawn_engine(app)
    except HTTPException as exc:
        state["error"] = str(exc.detail)
        return None
    return getattr(app.state, "engine_url", None)


_LIVE_WORKER_JOIN_TIMEOUT_S = 600.0


def _append_live_segments(app: FastAPI, db: Database, job_id: int, segments: list[Segment]) -> None:
    if not segments:
        return
    with app.state.live_lock:
        db.append_segments(job_id, segments)


def _handle_live_chunk(app: FastAPI, db: Database, pcm: np.ndarray) -> None:
    state = _active_capture_state(app)
    offset = int(state["chunk_start_seconds"])
    state["chunk_start_seconds"] = offset + (len(pcm) // SAMPLE_RATE)
    job_id = state.get("job_id")
    if job_id is None:
        return
    selected = _selected_model()
    if selected is not None and selected.backend == "cli":
        state["error"] = MEETING_CLI_HINT if state.get("kind") == "meeting" else LIVE_CLI_HINT
        return
    if selected is not None and selected.backend in {"openrouter", "custom", "http"}:
        fd, tmp = tempfile.mkstemp(prefix="gigaam_live_", suffix=".wav")
        os.close(fd)
        try:
            import soundfile as sf

            sf.write(tmp, np.asarray(pcm, dtype=np.float32), SAMPLE_RATE)
            duration_ms = int(len(pcm) * 1000 / SAMPLE_RATE) or 1
            segs = transcribe_http_file(
                backend=selected.backend,
                model_id=selected.id,
                audio_path=tmp,
                duration_ms=duration_ms,
            )
            _append_live_segments(
                app, db, job_id, offset_segments(segs, chunk_start_seconds=offset)
            )
        except Exception as exc:
            state["error"] = str(exc)
            db.set_error(job_id, str(exc))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return
    url = _ensure_engine_for_live(app)
    if not url:
        return
    try:
        payload = transcribe_chunk(url, np.asarray(pcm, dtype=np.float32).tolist())
        segs = offset_segments(_segments_from_engine(payload), offset)
        _append_live_segments(app, db, job_id, segs)
    except Exception as exc:
        state["error"] = str(exc)
        db.set_error(job_id, str(exc))


def _drain_live_session(
    app: FastAPI, db: Database, session: LiveSession, *, finalize: bool
) -> None:
    for chunk in session.take_ready_chunks():
        _handle_live_chunk(app, db, chunk)
    if finalize:
        tail = session.flush()
    else:
        tail = session.take_pending_tail()
    if tail is not None:
        _handle_live_chunk(app, db, tail)


def _live_worker(app: FastAPI, db: Database) -> None:
    state = _active_capture_state(app)
    stop_event: threading.Event = state["stop_event"]
    while True:
        session = state.get("session")
        if session is None:
            break
        for chunk in session.take_ready_chunks():
            _handle_live_chunk(app, db, chunk)
        if stop_event.is_set():
            _drain_live_session(app, db, session, finalize=True)
            break
        stop_event.wait(0.1)


def _stop_live_stream(app: FastAPI) -> None:
    state = app.state.live
    stream = state.get("stream")
    if stream is not None:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        state["stream"] = None
    _close_live_ingest(state)


def _finalize_capture_job(db: Database, state: dict, job_id: int) -> None:
    err = str(state.get("error") or "").strip()
    job = db.get_job(job_id) or {}
    if err or job.get("error_text"):
        if job.get("status") != JobStatus.CANCELLED.value:
            db.set_status(job_id, JobStatus.FAILED)
        return
    db.set_progress(job_id, 1)
    db.set_status(job_id, JobStatus.COMPLETED)


def create_ui_app(
    db: Database,
    engine: str | None,
    auto_start_engine: bool | None = None,
) -> FastAPI:
    if auto_start_engine is None:
        auto_start_engine = not is_cloud_only()
    from slysh.local_auth import install_ui_auth

    app = FastAPI()
    app.state.db = db
    install_ui_auth(app)

    @app.middleware("http")
    async def disable_static_cache(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    app.state.engine_url = engine
    app.state.engine_proc = None
    app.state.queue = None
    app.state.auto_start_engine = auto_start_engine
    app.state.engine_lock = threading.Lock()
    app.state.engine_starting = False
    app.state.remote_cancels = {}
    app.state.youtube_cancels = {}
    app.state.live = _empty_live_state()
    app.state.meeting = _empty_meeting_state()
    app.state.live_lock = threading.Lock()
    app.state.speaker_jobs = {}
    app.state.speaker_errors = {}
    app.state.speaker_started = {}
    app.state.speaker_cancels = {}
    app.state.speaker_ytdlp_procs = {}
    app.state.batch_runner = None
    app.state.asr_coordinator = AsrCoordinator()
    apply_preference(load_preference())

    @app.get("/api/library")
    def library() -> dict:
        grouped = db.list_jobs_grouped()
        batches = [
            _decorate_batch(app, batch, batch.get("jobs") or [])
            for batch in grouped["batches"]
        ]
        orphans = [
            _decorate_job(app, _job_payload(job)) for job in grouped["orphans"]
        ]
        return {"batches": batches, "orphans": orphans}

    @app.post("/api/library/check-existing")
    def library_check_existing(body: LibraryCheckExistingBody) -> dict:
        return _library_check_existing_payload(db, body)

    @app.get("/api/batches")
    def list_batches() -> list[dict]:
        return [
            _decorate_batch(app, batch, db.list_batch_jobs(int(batch["id"])))
            for batch in db.list_batches()
        ]

    @app.post("/api/batches")
    def create_batch(body: BatchCreateBody) -> dict:
        name = (body.name or "").strip() or f"Пакет {datetime.now().strftime('%d.%m')}"
        batch_id = db.create_batch(name, body.rules)
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, [])

    @app.get("/api/batches/{batch_id}")
    def get_batch(batch_id: int) -> dict:
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.patch("/api/batches/{batch_id}")
    def patch_batch(batch_id: int, body: BatchPatchBody) -> dict:
        _require_batch(db, batch_id)
        if body.rules is not None:
            if is_batch_active(app, batch_id):
                raise HTTPException(status_code=400, detail="Пакет сейчас выполняется.")
            db.update_batch(batch_id, rules=body.rules)
        if body.name is not None:
            db.update_batch(
                batch_id,
                name=body.name.strip() if body.name else None,
            )
        if body.archived is not None:
            if is_batch_active(app, batch_id):
                raise HTTPException(status_code=400, detail="Сначала остановите пакет.")
            db.set_batch_archived(batch_id, body.archived)
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.delete("/api/batches/{batch_id}")
    def delete_batch_route(batch_id: int) -> dict:
        _require_batch(db, batch_id)
        if is_batch_active(app, batch_id):
            raise HTTPException(status_code=400, detail="Сначала остановите пакет.")
        if not db.delete_batch(batch_id):
            raise HTTPException(status_code=404, detail="batch not found")
        return {"ok": True}

    @app.post("/api/batches/scan")
    def scan_batch_paths(body: BatchScanBody) -> dict:
        paths = scan_paths(body.paths, body.recursive)
        return {"count": len(paths), "paths": paths}

    @app.post("/api/batches/{batch_id}/items")
    def add_batch_items(batch_id: int, body: BatchItemsBody) -> dict:
        batch = _require_batch(db, batch_id)
        if is_youtube_batch_rules(batch.get("rules")):
            raise HTTPException(
                status_code=400,
                detail="В YouTube-пакет нельзя добавлять файлы. Используйте экран YouTube.",
            )
        resolved = scan_paths(body.paths, body.recursive)
        if not resolved:
            raise HTTPException(status_code=400, detail="Не найдено подходящих файлов.")
        existing = {
            job["source_path"] for job in db.list_batch_jobs(batch_id)
        }
        to_add = [path for path in resolved if path not in existing]
        if not to_add:
            raise HTTPException(status_code=400, detail="Все файлы уже в пакете.")
        for path in to_add:
            try:
                require_existing_file(path)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        db.add_jobs_to_batch(batch_id, to_add)
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.put("/api/batches/{batch_id}/reorder")
    def reorder_batch(batch_id: int, body: BatchReorderBody) -> dict:
        _require_batch(db, batch_id)
        if is_batch_active(app, batch_id):
            raise HTTPException(status_code=400, detail="Пакет сейчас выполняется.")
        expected = {job["id"] for job in db.list_batch_jobs(batch_id)}
        if set(body.job_ids) != expected:
            raise HTTPException(status_code=400, detail="Неверный список файлов пакета.")
        db.reorder_batch_jobs(batch_id, body.job_ids)
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.post("/api/batches/{batch_id}/start")
    def start_batch_route(batch_id: int) -> dict:
        batch = _require_batch(db, batch_id)
        if is_batch_active(app):
            raise HTTPException(status_code=400, detail="Уже выполняется другой пакет.")
        jobs = db.list_batch_jobs(batch_id)
        if not jobs:
            raise HTTPException(status_code=400, detail="В пакете нет заданий.")
        mismatch = _batch_job_kind_mismatch(batch, jobs)
        if mismatch:
            raise HTTPException(status_code=400, detail=mismatch)
        start_batch(
            app,
            db,
            batch_id,
            run_file_job=_run_file_asr_job,
            ensure_engine=_ensure_engine_url,
            run_engine_job=_run_engine_job,
            engine_cancel=engine_cancel,
        )
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.post("/api/batches/{batch_id}/pause")
    def pause_batch_route(batch_id: int) -> dict:
        _require_batch(db, batch_id)
        if not pause_batch(app, batch_id):
            raise HTTPException(status_code=400, detail="Пакет не выполняется.")
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.post("/api/batches/{batch_id}/export")
    def export_batch(batch_id: int, body: BatchExportBody) -> dict:
        _require_batch(db, batch_id)
        return _export_jobs_to_directory(db, db.list_batch_jobs(batch_id), body.fmt, body.directory)

    @app.post("/api/export-jobs")
    def export_jobs(body: JobsExportBody) -> dict:
        jobs = [_require_job(db, job_id) for job_id in body.job_ids]
        return _export_jobs_to_directory(db, jobs, body.fmt, body.directory)

    @app.post("/api/batches/{batch_id}/cancel")
    def cancel_batch_route(batch_id: int) -> dict:
        _require_batch(db, batch_id)
        url = getattr(app.state, "engine_url", None)
        if not cancel_batch(app, db, batch_id, engine_url=url, engine_cancel_fn=engine_cancel):
            raise HTTPException(status_code=400, detail="Пакет не выполняется.")
        batch = _require_batch(db, batch_id)
        return _decorate_batch(app, batch, db.list_batch_jobs(batch_id))

    @app.post("/api/jobs/{job_id}/remove-from-batch")
    def remove_from_batch(job_id: int) -> dict:
        job = _require_job(db, job_id)
        if job.get("batch_id") is None:
            raise HTTPException(status_code=400, detail="Файл не в пакете.")
        if is_batch_active(app, int(job["batch_id"])):
            raise HTTPException(status_code=400, detail="Пакет сейчас выполняется.")
        db.remove_job_from_batch(job_id)
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.get("/api/jobs")
    def list_jobs() -> list[dict]:
        return [_decorate_job(app, _job_payload(job)) for job in db.list_jobs()]

    @app.post("/api/jobs")
    def create_job(body: CreateJobBody) -> dict:
        try:
            source = require_existing_file(body.path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if body.batch_id is not None:
            batch = _require_batch(db, body.batch_id)
            if is_youtube_batch_rules(batch.get("rules")):
                raise HTTPException(
                    status_code=400,
                    detail="В YouTube-пакет нельзя добавлять файлы.",
                )
            job_id = db.create_job(
                JobKind.FILE,
                str(source),
                batch_id=body.batch_id,
            )
        else:
            job_id = db.create_job(JobKind.FILE, str(source))
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int) -> dict:
        segments = db.list_segments(job_id)
        job = _decorate_job(
            app,
            _job_payload(_require_job(db, job_id)),
            segments=segments,
            enrich_youtube=True,
        )
        if str(job.get("kind") or "") == "youtube":
            youtube_title = str(job.get("youtube", {}).get("title") or "").strip()
            source_title = str(job.get("source_title") or "").strip()
            if youtube_title and youtube_title != source_title:
                db.set_job_source_title(job_id, youtube_title)
                job["source_title"] = youtube_title
        names = db.list_speaker_names(job_id)
        job["segments"] = _segments_payload(segments, speaker_names=names)
        job["transcript"] = format_transcript(_display_segments(db, job_id, segments))
        return job

    @app.patch("/api/jobs/{job_id}")
    def patch_job(job_id: int, body: JobPatchBody) -> dict:
        job = _require_job(db, job_id)
        if body.archived is not None:
            if body.archived and job.get("status") != JobStatus.COMPLETED.value:
                raise HTTPException(
                    status_code=400,
                    detail="В архив можно перенести только готовые расшифровки.",
                )
            db.set_job_archived(job_id, body.archived)
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.patch("/api/jobs/{job_id}/segments")
    def patch_segments(job_id: int, body: PatchSegmentsBody) -> dict:
        _require_job(db, job_id)
        if body.transcript is not None:
            segments = parse_transcript(body.transcript)
        elif body.segments is not None:
            segments = [
                Segment(
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text=item.text,
                    speaker=item.speaker,
                )
                for item in body.segments
            ]
        else:
            raise HTTPException(
                status_code=400, detail="Нужен transcript или segments"
            )
        job = _require_job(db, job_id)
        if _transcription_blocks_editor_save(job):
            raise HTTPException(
                status_code=409,
                detail="Расшифровка ещё идёт. Дождитесь завершения или отмените задание.",
            )
        try:
            revision = db.replace_segments(
                job_id,
                segments,
                expected_revision=body.expected_revision,
            )
        except SegmentsRevisionConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Текст на сервере уже обновился (другая вкладка или расшифровка). "
                    f"Текущая версия: {exc.args[0] if exc.args else '?'}"
                ),
            ) from exc
        return {"ok": True, "segments_revision": revision}

    @app.post("/api/jobs/{job_id}/export")
    def export_job(job_id: int, body: ExportBody) -> dict:
        job = _require_job(db, job_id)
        try:
            out = Path(body.path) if body.path else suggested_export_path(job["source_path"], body.fmt)
            _write_job_export_file(db, job, out, body.fmt)
            db.set_last_export_path(job_id, str(out))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Не удалось сохранить файл: {exc}") from exc
        return {"path": str(out)}

    @app.put("/api/jobs/{job_id}/last-export-paths")
    def put_last_export_paths(job_id: int, body: ExportPathsBody) -> dict:
        _require_job(db, job_id)
        paths = [str(p).strip() for p in body.paths if str(p).strip()]
        if not paths:
            raise HTTPException(status_code=400, detail="Укажите хотя бы один путь.")
        db.set_last_export_paths(job_id, paths)
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.get("/api/jobs/{job_id}/media")
    def job_media(job_id: int) -> FileResponse:
        job = _require_job(db, job_id)
        path = Path(job["source_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        return FileResponse(path)

    @app.post("/api/jobs/{job_id}/retranscribe")
    def retranscribe(job_id: int, body: JobTranscribeBody = JobTranscribeBody()) -> dict:
        job = _require_job(db, job_id)
        if _is_youtube_job(job):
            method, language = load_job_ingest_meta(job_id)
            db.begin_transcription(job_id)
            _start_youtube_job(app, db, job_id, job["source_path"], method, language)
            return _decorate_job(app, _job_payload(_require_job(db, job_id)))
        _apply_transcribe_range(db, job_id, body)
        try:
            source = require_existing_file(job["source_path"])
        except ValueError as exc:
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _require_asr_ready()
        db.begin_transcription(job_id)
        _start_asr_job(app, db, job_id, str(source))
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.post("/api/jobs/{job_id}/start")
    def start_job(job_id: int, body: JobTranscribeBody = JobTranscribeBody()) -> dict:
        job = _require_job(db, job_id)
        if job["status"] in (JobStatus.RUNNING.value, JobStatus.QUEUED.value):
            return _decorate_job(app, _job_payload(job))
        if _is_youtube_job(job):
            method, language = load_job_ingest_meta(job_id)
            db.begin_transcription(job_id)
            _start_youtube_job(app, db, job_id, job["source_path"], method, language)
            return _decorate_job(app, _job_payload(_require_job(db, job_id)))
        _apply_transcribe_range(db, job_id, body)
        try:
            source = require_existing_file(job["source_path"])
        except ValueError as exc:
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _require_asr_ready()
        db.begin_transcription(job_id)
        _start_asr_job(app, db, job_id, str(source))
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: int) -> dict:
        _require_job(db, job_id)
        if job_id in getattr(app.state, "speaker_jobs", {}):
            app.state.speaker_jobs.pop(job_id, None)
        app.state.speaker_errors.pop(job_id, None)
        delete_job_ingest_meta(job_id)
        if not db.delete_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: int) -> dict:
        job = _require_job(db, job_id)
        logging.info("cancel requested for job %s status=%s", job_id, job.get("status"))
        queue = getattr(app.state, "queue", None)
        if queue is not None:
            queue.cancel(job_id)
        url = getattr(app.state, "engine_url", None)
        coord: AsrCoordinator = app.state.asr_coordinator
        if url and job["status"] == JobStatus.RUNNING.value and coord.local_job_id() == job_id:
            try:
                engine_cancel(url)
            except Exception:
                logging.exception("engine cancel failed for job %s", job_id)
        cancel_event = getattr(app.state, "remote_cancels", {}).get(job_id)
        if cancel_event is not None:
            cancel_event.set()
        youtube_cancel = getattr(app.state, "youtube_cancels", {}).get(job_id)
        if youtube_cancel is not None:
            youtube_cancel.set()
        if app.state.speaker_jobs.get(job_id) == "running":
            speaker_cancel = app.state.speaker_cancels.get(job_id)
            if speaker_cancel is not None:
                speaker_cancel.set()
            app.state.speaker_jobs.pop(job_id, None)
            app.state.speaker_started.pop(job_id, None)
            app.state.speaker_errors[job_id] = SPEAKER_CANCELLED_MESSAGE
            proc = app.state.speaker_ytdlp_procs.get(job_id)
            if proc is not None:
                try:
                    proc.terminate()
                except OSError:
                    logging.exception("speaker yt-dlp terminate failed for job %s", job_id)
        if job["status"] in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
            db.set_status(job_id, JobStatus.CANCELLED)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/speakers")
    def identify_speakers(job_id: int):
        if is_cloud_only():
            raise HTTPException(
                status_code=400,
                detail="Спикеры (NeMo) требуют локальных пакетов. Включите локальную расшифровку в настройках.",
            )
        job = _require_job(db, job_id)
        if job["status"] != JobStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Сначала дождитесь расшифровки.")
        if _is_youtube_job(job):
            raise HTTPException(
                status_code=400,
                detail="Распознавание спикеров для YouTube-транскриптов не поддерживается.",
            )
        if app.state.speaker_jobs.get(job_id) == "running":
            return {"ok": True, "started": True, "speakers": []}

        app.state.speaker_jobs[job_id] = "running"
        app.state.speaker_errors.pop(job_id, None)
        app.state.speaker_started[job_id] = time.monotonic()
        cancel_event = threading.Event()
        app.state.speaker_cancels[job_id] = cancel_event

        def is_cancelled() -> bool:
            return cancel_event.is_set()

        def work() -> None:
            try:
                module = importlib.import_module("slysh.speakers_msdd")
                labeled = assign_speakers(
                    db,
                    job_id,
                    module.MsddSpeakersBackend(),
                    cancelled=is_cancelled,
                )
                speakers: list[str] = []
                seen: set[str] = set()
                for seg in labeled:
                    if seg.speaker and seg.speaker not in seen:
                        seen.add(seg.speaker)
                        speakers.append(seg.speaker)
                app.state.speaker_errors.pop(job_id, None)
                logging.info("speakers ready for job %s: %s", job_id, speakers)
            except SpeakerCancelledError:
                logging.info("speakers cancelled for job %s", job_id)
                app.state.speaker_errors[job_id] = SPEAKER_CANCELLED_MESSAGE
            except Exception as exc:
                logging.exception("speakers failed for job %s", job_id)
                app.state.speaker_errors[job_id] = str(exc).strip() or "диаризация не удалась"
            finally:
                app.state.speaker_cancels.pop(job_id, None)
                app.state.speaker_ytdlp_procs.pop(job_id, None)
                app.state.speaker_jobs.pop(job_id, None)
                app.state.speaker_started.pop(job_id, None)

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "started": True, "speakers": []}

    @app.put("/api/jobs/{job_id}/speakers")
    def rename_speakers(job_id: int, body: dict[str, str]) -> dict:
        _require_job(db, job_id)
        for speaker_key, display_name in body.items():
            db.upsert_speaker(job_id, speaker_key, str(display_name).strip())
        return {"ok": True}

    @app.get("/api/app/info")
    def get_app_info() -> dict:
        return app_info()

    @app.post("/api/updates/check")
    def post_updates_check() -> dict:
        if not updates_enabled():
            raise HTTPException(
                status_code=400,
                detail="Проверка обновлений доступна только в установленной копии",
            )
        try:
            return check_for_updates()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/updates/status")
    def get_updates_status() -> dict:
        return download_status()

    @app.post("/api/updates/download")
    def post_updates_download() -> dict:
        if not updates_enabled():
            raise HTTPException(
                status_code=400,
                detail="Загрузка обновлений доступна только в установленной копии",
            )
        try:
            return start_download()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/updates/apply")
    def post_updates_apply() -> dict:
        if not updates_enabled():
            raise HTTPException(
                status_code=400,
                detail="Установка обновления доступна только в установленной копии",
            )
        try:
            result = apply_update()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        schedule_process_exit()
        return result

    @app.get("/api/status")
    def status() -> dict:
        selected = _selected_model()
        asr_id = selected.id if selected else load_asr_id()
        backend = selected.backend if selected else "gigaam"
        return {
            "engine": _engine_status(app),
            "model": _model_status(),
            "asr": asr_id,
            "asr_backend": backend,
            "can_download_local": engine_packages_ok() and not is_cloud_only(),
            "model_download": model_download_payload(),
        }

    @app.get("/api/setup")
    def get_setup() -> dict:
        return setup_status()

    @app.get("/api/setup/engine")
    def get_setup_engine() -> dict:
        return setup_status()

    @app.post("/api/setup/engine")
    def post_setup_engine(body: EngineSetupBody | None = None) -> dict:
        mark = bool(body and body.mark_pending_model)
        return start_engine_install(mark_pending_model=mark)

    @app.post("/api/setup/later")
    def post_setup_later() -> dict:
        dismiss_engine_setup()
        return setup_status()

    @app.post("/api/setup/model-later")
    def post_setup_model_later() -> dict:
        dismiss_model_setup()
        return setup_status()

    @app.post("/api/setup/cloud-only")
    def post_setup_cloud_only() -> dict:
        app.state.auto_start_engine = False
        extra = activate_cloud_only_mode()
        return {**setup_status(), **extra}

    @app.post("/api/setup/enable-local")
    def post_setup_enable_local() -> dict:
        enable_local_engine_mode()
        app.state.auto_start_engine = True
        return setup_status()

    @app.get("/api/models")
    def get_models() -> dict:
        items = [item.as_dict() for item in list_asr_models()]
        selected = _selected_model()
        selected_id = selected.id if selected else load_asr_id()
        local_ids = {item["id"] for item in items if item.get("kind") == "local"}
        remote_ids = {item["id"] for item in items if item.get("kind") != "local"}
        source = "provider" if selected_id in remote_ids else "local"
        local_id = load_asr_local_id()
        if local_id not in local_ids:
            local_id = next((item["id"] for item in items if item.get("kind") == "local"), "")
        remote_id = load_asr_remote_id()
        if remote_id not in remote_ids:
            remote_id = next(
                (
                    item["id"]
                    for item in items
                    if item.get("kind") != "local" and item.get("ready")
                ),
                next((item["id"] for item in items if item.get("kind") != "local"), ""),
            )
        return {
            "items": items,
            "selected": selected_id,
            "source": source,
            "selected_local": local_id,
            "selected_remote": remote_id,
            "engine_mode": load_engine_mode(),
            "cloud_only": is_cloud_only(),
            "roots": [str(path) for path in catalog_roots()],
            "project_models": str(project_models_dir()),
        }

    @app.put("/api/models")
    def put_models(body: AsrModelBody) -> dict:
        item = get_model(body.id)
        if item is None:
            raise HTTPException(status_code=400, detail="Модель не найдена.")
        if is_cloud_only() and item.kind == "local":
            raise HTTPException(
                status_code=400,
                detail="Включён режим «только облако». Нажмите «Включить локальную расшифровку» в настройках.",
            )
        if not item.ready:
            detail = item.hint or "Провайдер не настроен."
            if item.kind == "local":
                detail = "Файлы модели не найдены."
            raise HTTPException(status_code=400, detail=detail)
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки и спикеров, затем смените модель.",
            )
        save_asr_id(item.id)
        restarted = False
        if item.backend in ("gigaam", "whisper") and getattr(app.state, "engine_proc", None) is not None:
            _stop_engine(app)
            restarted = True
        payload = get_models()
        payload["engine"] = _engine_status(app)
        payload["engine_restarted"] = restarted
        return payload

    @app.get("/api/providers")
    def get_providers() -> dict:
        return public_providers()

    @app.get("/api/providers/apify")
    def get_apify() -> dict:
        return public_apify()

    @app.put("/api/providers/apify")
    def put_apify(body: ApifyBody) -> dict:
        save_apify(api_key=body.api_key)
        return public_apify()

    def _save_proxy_from_body(body: ProxyBody) -> dict:
        try:
            save_proxy_config(
                enabled=body.enabled,
                host=body.host,
                port=body.port,
                username=body.username,
                password=body.password,
                keep_password=body.password is None,
                targets=body.targets,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_proxy_config()

    @app.get("/api/proxy")
    @app.get("/api/providers/proxy")
    def get_proxy() -> dict:
        return public_proxy_config()

    @app.put("/api/proxy")
    @app.put("/api/providers/proxy")
    def put_proxy(body: ProxyBody) -> dict:
        return _save_proxy_from_body(body)

    @app.put("/api/providers/openrouter")
    def put_openrouter(body: OpenRouterBody) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки, затем измените провайдера.",
            )
        save_openrouter(api_key=body.api_key, model=body.model)
        return public_providers()

    @app.post("/api/providers/openrouter/refresh")
    def refresh_openrouter() -> dict:
        try:
            fetch_openrouter_stt_models()
        except RemoteAsrError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_providers()

    @app.api_route("/api/providers/http/{preset_id}", methods=["PUT", "POST"])
    def put_http_preset(preset_id: str, body: HttpPresetBody) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки, затем измените провайдера.",
            )
        if get_http_preset(preset_id) is None:
            raise HTTPException(status_code=404, detail="Сервис не найден.")
        try:
            save_http_preset(preset_id, api_key=body.api_key, model=body.model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_providers()

    @app.post("/api/providers/custom")
    def add_custom_provider(body: CustomProviderBody) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки, затем измените провайдера.",
            )
        try:
            upsert_custom_provider(
                provider_id=body.id,
                name=body.name,
                endpoint=body.endpoint,
                model=body.model,
                api_key=body.api_key,
                protocol=body.protocol,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_providers()

    @app.put("/api/providers/custom/{provider_id}")
    def update_custom_provider(provider_id: str, body: CustomProviderBody) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки, затем измените провайдера.",
            )
        if get_custom_provider(provider_id) is None:
            raise HTTPException(status_code=404, detail="Провайдер не найден.")
        try:
            upsert_custom_provider(
                provider_id=provider_id,
                name=body.name,
                endpoint=body.endpoint,
                model=body.model,
                api_key=body.api_key,
                keep_key=body.api_key is None,
                protocol=body.protocol,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return public_providers()

    @app.delete("/api/providers/custom/{provider_id}")
    def remove_custom_provider(provider_id: str) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки, затем измените провайдера.",
            )
        if not delete_custom_provider(provider_id):
            raise HTTPException(status_code=404, detail="Провайдер не найден.")
        selected = load_asr_id()
        if selected == f"custom:{provider_id}":
            save_asr_id(GIGAAM_ID)
        return public_providers()

    @app.get("/api/providers/cli")
    def get_cli_providers() -> dict:
        return {"gemini": gemini_status()}

    @app.get("/api/locale")
    def get_ui_locale(hint: str | None = None) -> dict:
        return {"ui_locale": resolve_ui_locale(hint)}

    @app.put("/api/locale")
    def put_ui_locale(body: UiLocaleBody) -> dict:
        try:
            locale = save_ui_locale(body.ui_locale)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ui_locale": locale}

    @app.get("/api/compute")
    def get_compute() -> dict:
        payload = compute_payload()
        payload["engine"] = _engine_status(app)
        return payload

    @app.put("/api/compute")
    def put_compute(body: ComputeBody) -> dict:
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки и спикеров, затем смените CPU/GPU.",
            )
        try:
            pref = save_preference(body.preference)
            apply_preference(pref)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        restarted = False
        if getattr(app.state, "engine_proc", None) is not None:
            _stop_engine(app)
            restarted = True
        payload = compute_payload()
        payload["engine"] = _engine_status(app)
        payload["engine_restarted"] = restarted
        return payload

    @app.post("/api/open-path")
    def open_saved_path(body: OpenPathBody) -> dict:
        try:
            resolve_existing(body.path)
            if body.reveal:
                reveal_in_folder(body.path)
            else:
                open_file(body.path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Файл не найден.") from None
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/model/download")
    def get_model_download() -> dict:
        return model_download_payload()

    @app.post("/api/model/download")
    def download_model(body: ModelDownloadBody | None = None):
        model_id = GIGAAM_ID
        if body is not None and body.id:
            model_id = str(body.id).strip()
        if is_cloud_only():
            raise HTTPException(
                status_code=400,
                detail="Включён режим «только облако». Скачивание локальных моделей недоступно.",
            )
        if not engine_packages_ok():
            raise HTTPException(
                status_code=400,
                detail="Сначала установите локальные пакеты расшифровки (torch и движки).",
            )
        if _pipeline_busy(app, db):
            raise HTTPException(
                status_code=400,
                detail="Дождитесь конца расшифровки и спикеров, затем скачайте модель.",
            )
        if not is_downloadable_local_id(model_id):
            raise HTTPException(status_code=400, detail="Модель не поддерживает скачивание.")
        item = get_model(model_id)
        if item is not None and item.ready:
            return {"status": "ready", "id": model_id}
        try:
            start_model_download(model_id)
            dismiss_model_setup()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            return JSONResponse(status_code=500, content={"error": str(exc)})
        return {"status": "started", "id": model_id}

    @app.post("/api/engine/start")
    def start_engine() -> dict[str, int]:
        return _spawn_engine(app)

    @app.get("/api/mics")
    def list_mics(refresh: bool = False) -> list[dict]:
        if refresh:
            if _live_is_busy(app) or _meeting_is_busy(app):
                raise HTTPException(
                    status_code=400,
                    detail="Остановите запись, чтобы обновить список устройств.",
                )
            refresh_audio_devices()
        return _list_input_mics(app, force=refresh)

    @app.get("/api/live/status")
    def live_status() -> dict:
        return _live_status_payload(app, db, app.state.live)

    @app.post("/api/live/start")
    def live_start(body: LiveStartBody | None = None) -> dict:
        body = body or LiveStartBody()
        if _meeting_is_busy(app):
            raise HTTPException(status_code=400, detail=MEETING_BUSY_HINT)
        if _live_session_active(app.state.live):
            raise HTTPException(status_code=400, detail=LIVE_ALREADY_HINT)
        selected = _selected_model()
        if selected is not None and selected.backend == "cli":
            raise HTTPException(status_code=400, detail=LIVE_CLI_HINT)
        _require_asr_ready()
        mics = _list_input_mics(app)
        if not mics:
            raise HTTPException(status_code=400, detail=NO_MIC_HINT)
        wav_path = recordings_dir() / datetime.now().strftime("live-%Y%m%d-%H%M%S.wav")
        session = LiveSession(wav_path=wav_path)
        job_id = db.create_job(JobKind.LIVE, str(wav_path))
        db.set_status(job_id, JobStatus.RUNNING)
        stop_event = threading.Event()
        app.state.live = {
            "listening": True,
            "paused": False,
            "session": session,
            "stream": None,
            "ingest": None,
            "thread": None,
            "stop_event": stop_event,
            "job_id": job_id,
            "device_id": body.device_id,
            "rms": 0.0,
            "error": None,
            "chunk_start_seconds": 0,
            "paused_at": None,
            "total_paused_s": 0.0,
            "kind": "live",
        }
        _ensure_live_ingest(app.state.live)

        def _callback_for_rate(capture_rate: int):
            return _live_mic_callback(app, capture_rate)

        try:
            stream, _capture_rate = open_mic_input_stream(body.device_id, _callback_for_rate)
            stream.start()
        except MeetingCaptureError as exc:
            session.flush()
            _close_live_ingest(app.state.live)
            app.state.live = _empty_live_state()
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            session.flush()
            _close_live_ingest(app.state.live)
            app.state.live = _empty_live_state()
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        app.state.live["stream"] = stream
        worker = threading.Thread(target=_live_worker, args=(app, db), daemon=True)
        app.state.live["thread"] = worker
        worker.start()
        return _job_payload(_require_job(db, job_id))

    @app.post("/api/live/pause")
    def live_pause() -> dict:
        state = app.state.live
        if not _live_session_active(state):
            raise HTTPException(status_code=400, detail=LIVE_NOT_ACTIVE_HINT)
        if state.get("paused"):
            raise HTTPException(status_code=400, detail=LIVE_ALREADY_PAUSED_HINT)
        state["paused"] = True
        state["paused_at"] = time.monotonic()
        state["listening"] = False
        state["rms"] = 0.0
        _stop_live_stream(app)
        session = state.get("session")
        if session is not None:
            _drain_live_session(app, db, session, finalize=False)
        return _live_status_payload(app, db, state)

    @app.post("/api/live/resume")
    def live_resume() -> dict:
        state = app.state.live
        if not _live_session_active(state):
            raise HTTPException(status_code=400, detail=LIVE_NOT_ACTIVE_HINT)
        if not state.get("paused"):
            raise HTTPException(status_code=400, detail=LIVE_NOT_PAUSED_HINT)
        paused_at = state.get("paused_at")
        if paused_at is not None:
            state["total_paused_s"] = float(state.get("total_paused_s") or 0.0) + (
                time.monotonic() - float(paused_at)
            )
        state["paused"] = False
        state["paused_at"] = None
        _ensure_live_ingest(state)

        def _callback_for_rate(capture_rate: int):
            return _live_mic_callback(app, capture_rate)

        try:
            stream, _capture_rate = open_mic_input_stream(state.get("device_id"), _callback_for_rate)
            stream.start()
        except MeetingCaptureError as exc:
            state["paused"] = True
            state["paused_at"] = time.monotonic()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            state["paused"] = True
            state["paused_at"] = time.monotonic()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state["stream"] = stream
        state["listening"] = True
        return _live_status_payload(app, db, state)

    @app.post("/api/live/stop")
    def live_stop() -> dict:
        state = app.state.live
        job_id = state.get("job_id")
        state["listening"] = False
        state["paused"] = False
        state["paused_at"] = None
        if state.get("stop_event") is not None:
            state["stop_event"].set()
        _stop_live_stream(app)
        thread = state.get("thread")
        if thread is not None:
            thread.join(timeout=_LIVE_WORKER_JOIN_TIMEOUT_S)
            state["thread"] = None
        state["session"] = None
        state["device_id"] = None
        if job_id is not None:
            _finalize_capture_job(db, state, job_id)
            names = db.list_speaker_names(job_id)
            payload = _job_payload(_require_job(db, job_id))
            payload["segments"] = _segments_payload(
                db.list_segments(job_id), speaker_names=names
            )
            return payload
        return {"ok": True}

    @app.post("/api/live/clear")
    def live_clear() -> dict:
        state = app.state.live
        if _live_session_active(state):
            raise HTTPException(status_code=400, detail="Сначала остановите запись.")
        state["job_id"] = None
        state["error"] = None
        return {"ok": True}

    @app.get("/api/meeting/devices")
    def meeting_devices(refresh: bool = False) -> dict:
        if refresh:
            if _live_is_busy(app) or _meeting_is_busy(app):
                raise HTTPException(
                    status_code=400,
                    detail="Остановите запись, чтобы обновить список устройств.",
                )
            refresh_audio_devices()
        outputs = list_output_devices()
        mics = _list_input_mics(app, force=refresh)
        return {
            "outputs": outputs,
            "mics": mics,
            "loopback_supported": loopback_supported(),
            "default_output_id": outputs[0]["id"] if outputs else None,
            "default_input_id": mics[0]["id"] if mics else None,
        }

    @app.get("/api/meeting/status")
    def meeting_status() -> dict:
        return _meeting_status_payload(app, db, app.state.meeting)

    @app.post("/api/meeting/start")
    def meeting_start(body: MeetingStartBody | None = None) -> dict:
        body = body or MeetingStartBody()
        if _live_is_busy(app):
            raise HTTPException(status_code=400, detail=LIVE_BUSY_HINT)
        if _meeting_is_busy(app):
            raise HTTPException(status_code=400, detail=MEETING_ALREADY_HINT)
        selected = _selected_model()
        if selected is not None and selected.backend == "cli":
            raise HTTPException(status_code=400, detail=MEETING_CLI_HINT)
        _require_asr_ready()
        if not loopback_supported():
            raise HTTPException(status_code=400, detail=NOT_WINDOWS_HINT)
        outputs = list_output_devices()
        if not outputs:
            raise HTTPException(status_code=400, detail=NO_OUTPUT_HINT)
        include_mic = bool(body.include_mic)
        if include_mic:
            mics = _list_input_mics(app)
            if not mics:
                raise HTTPException(status_code=400, detail=NO_MIC_HINT)
        wav_path = recordings_dir() / datetime.now().strftime("meeting-%Y%m%d-%H%M%S.wav")
        session = LiveSession(wav_path=wav_path)
        job_id = db.create_job(JobKind.MEETING, str(wav_path))
        db.set_status(job_id, JobStatus.RUNNING)
        stop_event = threading.Event()
        app.state.meeting = {
            "listening": True,
            "paused": False,
            "session": session,
            "capture": None,
            "thread": None,
            "stop_event": stop_event,
            "job_id": job_id,
            "rms_mic": 0.0,
            "rms_system": 0.0,
            "error": None,
            "chunk_start_seconds": 0,
            "started_monotonic": time.monotonic(),
            "paused_at": None,
            "total_paused_s": 0.0,
            "include_mic": include_mic,
            "kind": "meeting",
        }
        capture = MeetingCapture(
            session=session,
            output_device_id=body.output_device_id,
            mic_device_id=body.mic_device_id,
            include_mic=include_mic,
            rms_holder=app.state.meeting,
        )
        try:
            capture.start()
        except MeetingCaptureError as exc:
            session.flush()
            app.state.meeting = _empty_meeting_state()
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            session.flush()
            app.state.meeting = _empty_meeting_state()
            db.set_error(job_id, str(exc))
            db.set_status(job_id, JobStatus.FAILED)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        app.state.meeting["capture"] = capture
        worker = threading.Thread(target=_live_worker, args=(app, db), daemon=True)
        app.state.meeting["thread"] = worker
        worker.start()
        return _job_payload(_require_job(db, job_id))

    @app.post("/api/meeting/pause")
    def meeting_pause() -> dict:
        state = app.state.meeting
        if not _meeting_session_active(state):
            raise HTTPException(status_code=400, detail=MEETING_NOT_ACTIVE_HINT)
        if state.get("paused"):
            raise HTTPException(status_code=400, detail=MEETING_ALREADY_PAUSED_HINT)
        capture = state.get("capture")
        if capture is not None:
            capture.pause()
        state["paused"] = True
        state["paused_at"] = time.monotonic()
        state["rms_mic"] = 0.0
        state["rms_system"] = 0.0
        return _meeting_status_payload(app, db, state)

    @app.post("/api/meeting/resume")
    def meeting_resume() -> dict:
        state = app.state.meeting
        if not _meeting_session_active(state):
            raise HTTPException(status_code=400, detail=MEETING_NOT_ACTIVE_HINT)
        if not state.get("paused"):
            raise HTTPException(status_code=400, detail=MEETING_NOT_PAUSED_HINT)
        paused_at = state.get("paused_at")
        if paused_at is not None:
            state["total_paused_s"] = float(state.get("total_paused_s") or 0.0) + (
                time.monotonic() - float(paused_at)
            )
        state["paused"] = False
        state["paused_at"] = None
        capture = state.get("capture")
        if capture is not None:
            capture.resume()
        return _meeting_status_payload(app, db, state)

    @app.post("/api/meeting/stop")
    def meeting_stop() -> dict:
        state = app.state.meeting
        job_id = state.get("job_id")
        state["listening"] = False
        state["paused"] = False
        state["paused_at"] = None
        if state.get("stop_event") is not None:
            state["stop_event"].set()
        capture = state.get("capture")
        if capture is not None:
            try:
                capture.stop()
            except Exception:
                pass
            state["capture"] = None
        thread = state.get("thread")
        if thread is not None:
            thread.join(timeout=_LIVE_WORKER_JOIN_TIMEOUT_S)
            state["thread"] = None
        state["session"] = None
        if job_id is not None:
            _finalize_capture_job(db, app.state.meeting, job_id)
            names = db.list_speaker_names(job_id)
            payload = _job_payload(_require_job(db, job_id))
            payload["segments"] = _segments_payload(
                db.list_segments(job_id), speaker_names=names
            )
            return payload
        return {"ok": True}

    @app.post("/api/meeting/clear")
    def meeting_clear() -> dict:
        state = app.state.meeting
        if _meeting_session_active(state):
            raise HTTPException(status_code=400, detail="Сначала остановите запись.")
        state["job_id"] = None
        state["error"] = None
        return {"ok": True}

    @app.get("/api/youtube/status")
    def youtube_get_status() -> dict:
        payload = youtube_status()
        payload["cookies"] = cookies_status()
        payload["apify"] = public_apify()
        payload["batch_api"] = True
        payload["batch_resolve_api"] = True
        return payload

    @app.get("/api/youtube/cookies/browsers")
    def youtube_cookies_browsers() -> dict:
        return list_browser_profiles()

    @app.post("/api/youtube/cookies/extract")
    def youtube_cookies_extract(body: YoutubeCookiesExtractBody) -> dict:
        try:
            return extract_cookies(body.browser, body.profile)
        except YoutubeCookiesError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logging.exception("youtube cookies extract failed")
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось извлечь cookies: {exc}",
            ) from exc

    @app.post("/api/youtube/cookies/import")
    def youtube_cookies_import(body: YoutubeCookiesImportBody) -> dict:
        try:
            return import_cookies_file(body.path)
        except YoutubeCookiesError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/youtube/batch/resolve")
    def youtube_batch_resolve(body: YoutubeBatchResolveBody) -> dict:
        videos = _attach_youtube_existing_jobs(db, _resolve_youtube_videos(body))
        return {"count": len(videos), "videos": videos}

    @app.post("/api/youtube/batch")
    def youtube_batch_create(body: YoutubeBatchCreateBody) -> dict:
        return _create_youtube_batch(app, db, body)

    @app.post("/api/youtube/batch/create")
    def youtube_batch_create_alias(body: YoutubeBatchCreateBody) -> dict:
        return _create_youtube_batch(app, db, body)

    @app.post("/api/youtube/ingest")
    def youtube_ingest(body: YoutubeIngestBody) -> dict:
        method = str(body.method or "apify").strip().lower()
        if method not in {"apify", "ytdlp"}:
            raise HTTPException(status_code=400, detail="Способ должен быть apify или ytdlp.")
        language = str(body.language or "ru").strip() or "ru"
        try:
            url, _video_id = normalize_youtube_url(body.url)
        except YoutubeIngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job_id = db.create_job(JobKind.YOUTUBE, url)
        save_job_ingest_meta(job_id, method, language)
        db.begin_transcription(job_id)
        _start_youtube_job(app, db, job_id, url, method, language)
        return _decorate_job(app, _job_payload(_require_job(db, job_id)))

    ui_dir = web_dir()
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="web")

    return app


def __getattr__(name: str):
    if name == "sd":
        from slysh.sounddevice_lazy import sd

        return sd
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
