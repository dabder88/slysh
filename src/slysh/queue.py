from __future__ import annotations

from collections.abc import Callable

from slysh.db import Database
from slysh.decode import decode_pcm_16k_mono
from slysh.models import JobStatus
from slysh.transcribe import FilePipeline

GPU_OOM_MESSAGE = (
    "Не хватило памяти GPU. Закройте другие программы или работайте без спикеров."
)
DECODE_ERROR_MESSAGE = "Файл не читается или ffmpeg не найден."


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, FileNotFoundError):
        return DECODE_ERROR_MESSAGE
    text = str(exc).lower()
    if "oom" in text or "cuda" in text:
        return GPU_OOM_MESSAGE
    return str(exc)


def _default_decode(path: str):
    pcm, _sr = decode_pcm_16k_mono(path)
    return pcm


class JobQueue:
    def __init__(self, db: Database, pipeline: FilePipeline) -> None:
        self.db = db
        self.pipeline = pipeline
        self._cancelled: set[int] = set()
        self._decode: Callable[[str], object] = _default_decode

    def cancel(self, job_id: int) -> None:
        self._cancelled.add(job_id)

    def run_until_idle(self) -> None:
        for job in self.db.list_queued_jobs():
            job_id = int(job["id"])
            if job_id in self._cancelled:
                self.db.set_status(job_id, JobStatus.CANCELLED)
                continue
            self.db.set_status(job_id, JobStatus.RUNNING)
            try:
                status, segs = self.pipeline.transcribe(
                    job["source_path"],
                    cancelled=lambda jid=job_id: jid in self._cancelled,
                    on_progress=lambda p, jid=job_id: self.db.set_progress(jid, p),
                    decode=self._decode,
                    start_ms=job.get("range_start_ms"),
                    end_ms=job.get("range_end_ms"),
                )
            except Exception as exc:
                self.db.set_error(job_id, _error_message(exc))
                self.db.set_status(job_id, JobStatus.FAILED)
                continue
            if status == "cancelled" or job_id in self._cancelled:
                self.db.replace_segments(job_id, segs)
                self.db.set_status(job_id, JobStatus.CANCELLED)
                continue
            self.db.replace_segments(job_id, segs)
            self.db.set_status(job_id, JobStatus.COMPLETED)
