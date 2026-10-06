from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

from slysh.batch_rules import rules_from_json, rules_to_json
from slysh.models import BatchStatus, JobKind, JobStatus, Segment
from slysh.youtube_ingest import extract_video_id


def _normalize_file_path_key(path: str) -> str:
    if os.name == "nt":
        return os.path.normcase(os.path.normpath(path))
    return os.path.normpath(path)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  rules_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  error_text TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  last_export_path TEXT,
  device_used TEXT,
  batch_id INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  range_start_ms INTEGER,
  range_end_ms INTEGER,
  FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL,
  speaker TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(id)
);
CREATE TABLE IF NOT EXISTS speakers (
  job_id INTEGER NOT NULL,
  speaker_key TEXT NOT NULL,
  display_name TEXT NOT NULL,
  PRIMARY KEY(job_id, speaker_key)
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


class SegmentsRevisionConflictError(Exception):
    """Editor save expected_revision does not match the job row."""


@dataclass(frozen=True)
class SegmentSnapshotRow:
    row_id: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None


@dataclass(frozen=True)
class SegmentsSnapshot:
    revision: int
    rows: tuple[SegmentSnapshotRow, ...]


class Database:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(jobs)")}
        if "started_at" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN started_at TEXT")
        if "last_export_path" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN last_export_path TEXT")
        if "last_export_paths" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN last_export_paths TEXT")
        if "batch_id" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN batch_id INTEGER")
        if "position" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        if "archived" not in cols:
            self._conn.execute(
                "ALTER TABLE jobs ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
        if "range_start_ms" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN range_start_ms INTEGER")
        if "range_end_ms" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN range_end_ms INTEGER")
        if "source_title" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN source_title TEXT")
        if "run_id" not in cols:
            self._conn.execute(
                "ALTER TABLE jobs ADD COLUMN run_id INTEGER NOT NULL DEFAULT 0"
            )
        if "segments_revision" not in cols:
            self._conn.execute(
                "ALTER TABLE jobs ADD COLUMN segments_revision INTEGER NOT NULL DEFAULT 0"
            )
        if "asr_model_id" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN asr_model_id TEXT")
        if "asr_backend" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN asr_backend TEXT")
        if "media_duration_s" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN media_duration_s REAL")
        self._backfill_media_duration_s()
        batch_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(batches)")}
        if "archived" not in batch_cols:
            self._conn.execute(
                "ALTER TABLE batches ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batches (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              rules_json TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_youtube_meta (
              job_id INTEGER PRIMARY KEY,
              method TEXT NOT NULL DEFAULT 'ytdlp',
              language TEXT NOT NULL DEFAULT 'ru',
              video_json TEXT NOT NULL DEFAULT '{}',
              FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
            """
        )
        self._migrate_youtube_meta_from_file()

    def _migrate_youtube_meta_from_file(self) -> None:
        from slysh.paths import youtube_dir

        path = youtube_dir() / "job-meta.json"
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logging.warning("skip youtube meta file migration: unreadable %s", path)
            return
        if not isinstance(raw, dict):
            return
        for key, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            try:
                job_id = int(key)
            except (TypeError, ValueError):
                continue
            if self.get_job(job_id) is None:
                continue
            method = str(entry.get("method") or "ytdlp").strip().lower()
            if method not in {"apify", "ytdlp"}:
                method = "ytdlp"
            language = str(entry.get("language") or "ru").strip() or "ru"
            video = entry.get("video")
            video_dict = dict(video) if isinstance(video, dict) else {}
            self.upsert_job_youtube_meta(job_id, method, language, video_dict)
        backup = path.with_name("job-meta.json.bak-migrated")
        try:
            if backup.is_file():
                backup.unlink()
            path.rename(backup)
        except OSError:
            logging.warning("could not archive migrated youtube meta file %s", path)

    @_locked
    def get_job_youtube_meta(self, job_id: int) -> dict | None:
        row = self._conn.execute(
            """
            SELECT method, language, video_json
            FROM job_youtube_meta
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            video = json.loads(row["video_json"] or "{}")
        except json.JSONDecodeError:
            video = {}
        if not isinstance(video, dict):
            video = {}
        return {
            "method": str(row["method"] or "ytdlp"),
            "language": str(row["language"] or "ru"),
            "video": video,
        }

    @_locked
    def upsert_job_youtube_meta(
        self,
        job_id: int,
        method: str,
        language: str,
        video: dict | None = None,
    ) -> None:
        existing = self.get_job_youtube_meta(job_id) or {}
        method_value = str(method or existing.get("method") or "ytdlp").strip().lower()
        if method_value not in {"apify", "ytdlp"}:
            method_value = "ytdlp"
        language_value = str(language or existing.get("language") or "ru").strip() or "ru"
        if video is None:
            video_payload = dict(existing.get("video") or {})
        else:
            video_payload = dict(video)
        payload = json.dumps(video_payload, ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO job_youtube_meta (job_id, method, language, video_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
              method = excluded.method,
              language = excluded.language,
              video_json = excluded.video_json
            """,
            (job_id, method_value, language_value, payload),
        )
        self._conn.commit()

    @_locked
    def delete_job_youtube_meta(self, job_id: int) -> None:
        self._conn.execute(
            "DELETE FROM job_youtube_meta WHERE job_id = ?",
            (job_id,),
        )
        self._conn.commit()

    @_locked
    def create_batch(self, name: str, rules: dict | None = None) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO batches (name, rules_json, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, rules_to_json(rules), BatchStatus.IDLE.value, _utc_now_iso()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    @_locked
    def get_batch(self, batch_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["rules"] = rules_from_json(data.get("rules_json"))
        return data

    @_locked
    def list_batches(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM batches ORDER BY id DESC"
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            data = dict(row)
            data["rules"] = rules_from_json(data.get("rules_json"))
            out.append(data)
        return out

    @_locked
    def update_batch(
        self,
        batch_id: int,
        *,
        name: str | None = None,
        rules: dict | None = None,
        status: BatchStatus | None = None,
    ) -> bool:
        if self.get_batch(batch_id) is None:
            return False
        if name is not None:
            self._conn.execute(
                "UPDATE batches SET name = ? WHERE id = ?",
                (name, batch_id),
            )
        if rules is not None:
            self._conn.execute(
                "UPDATE batches SET rules_json = ? WHERE id = ?",
                (rules_to_json(rules), batch_id),
            )
        if status is not None:
            self._conn.execute(
                "UPDATE batches SET status = ? WHERE id = ?",
                (status.value, batch_id),
            )
        self._conn.commit()
        return True

    @_locked
    def delete_batch(self, batch_id: int) -> bool:
        if self.get_batch(batch_id) is None:
            return False
        job_ids = [
            row["id"]
            for row in self._conn.execute(
                "SELECT id FROM jobs WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
        ]
        for job_id in job_ids:
            self._conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
            self._conn.execute("DELETE FROM speakers WHERE job_id = ?", (job_id,))
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self._conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        self._conn.commit()
        return True

    def _speaker_stats_map(self, job_ids: list[int]) -> dict[int, int]:
        if not job_ids:
            return {}
        placeholders = ",".join("?" * len(job_ids))
        rows = self._conn.execute(
            f"""
            SELECT job_id, COUNT(DISTINCT speaker) AS speaker_count
            FROM segments
            WHERE job_id IN ({placeholders})
              AND speaker IS NOT NULL
              AND trim(speaker) != ''
            GROUP BY job_id
            """,
            job_ids,
        ).fetchall()
        return {int(row["job_id"]): int(row["speaker_count"]) for row in rows}

    def _backfill_media_duration_s(self) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET media_duration_s = (
                SELECT CAST(MAX(end_ms) AS REAL) / 1000.0
                FROM segments
                WHERE segments.job_id = jobs.id
            )
            WHERE media_duration_s IS NULL
              AND EXISTS (
                SELECT 1 FROM segments WHERE segments.job_id = jobs.id
              )
            """
        )
        self._conn.execute(
            """
            UPDATE jobs
            SET media_duration_s = (
                CAST(range_end_ms AS REAL) - CAST(range_start_ms AS REAL)
            ) / 1000.0
            WHERE media_duration_s IS NULL
              AND range_start_ms IS NOT NULL
              AND range_end_ms IS NOT NULL
              AND range_end_ms > range_start_ms
            """
        )

    def _segment_max_end_ms_map(self, job_ids: list[int]) -> dict[int, int]:
        if not job_ids:
            return {}
        placeholders = ",".join("?" * len(job_ids))
        rows = self._conn.execute(
            f"""
            SELECT job_id, MAX(end_ms) AS max_end
            FROM segments
            WHERE job_id IN ({placeholders})
            GROUP BY job_id
            """,
            job_ids,
        ).fetchall()
        out: dict[int, int] = {}
        for row in rows:
            if row["max_end"] is not None:
                out[int(row["job_id"])] = int(row["max_end"])
        return out

    def _with_speaker_stats(self, jobs: list[dict]) -> list[dict]:
        if not jobs:
            return jobs
        job_ids = [int(job["id"]) for job in jobs]
        counts = self._speaker_stats_map(job_ids)
        max_ends = self._segment_max_end_ms_map(job_ids)
        for job in jobs:
            jid = int(job["id"])
            n = counts.get(jid, 0)
            job["speaker_count"] = n
            job["has_speakers"] = n > 0
            max_end = max_ends.get(jid)
            if max_end is not None:
                job["segment_max_end_ms"] = max_end
        return jobs

    @_locked
    def list_batch_jobs(self, batch_id: int) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE batch_id = ?
            ORDER BY position ASC, id ASC
            """,
            (batch_id,),
        ).fetchall()
        return self._with_speaker_stats([dict(row) for row in rows])

    @_locked
    def list_orphan_jobs(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE batch_id IS NULL
            ORDER BY id DESC
            """
        ).fetchall()
        return self._with_speaker_stats([dict(row) for row in rows])

    @_locked
    def list_jobs_grouped(self) -> dict:
        batches = self.list_batches()
        grouped: list[dict] = []
        for batch in batches:
            jobs = self.list_batch_jobs(int(batch["id"]))
            grouped.append({**batch, "jobs": jobs})
        return {"batches": grouped, "orphans": self.list_orphan_jobs()}

    @_locked
    def _next_batch_position(self, batch_id: int) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS max_pos FROM jobs WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        return int(row["max_pos"]) + 1

    @_locked
    def reorder_batch_jobs(self, batch_id: int, job_ids: list[int]) -> None:
        for position, job_id in enumerate(job_ids):
            self._conn.execute(
                """
                UPDATE jobs SET position = ?
                WHERE id = ? AND batch_id = ?
                """,
                (position, job_id, batch_id),
            )
        self._conn.commit()

    @_locked
    def remove_job_from_batch(self, job_id: int) -> bool:
        job = self.get_job(job_id)
        if job is None or job.get("batch_id") is None:
            return False
        self._conn.execute(
            "UPDATE jobs SET batch_id = NULL, position = 0 WHERE id = ?",
            (job_id,),
        )
        self._conn.commit()
        return True

    @_locked
    def create_job(
        self,
        kind: JobKind,
        source_path: str,
        *,
        batch_id: int | None = None,
        position: int | None = None,
    ) -> int:
        pos = position
        if batch_id is not None and pos is None:
            pos = self._next_batch_position(batch_id)
        if pos is None:
            pos = 0
        cur = self._conn.execute(
            """
            INSERT INTO jobs (kind, source_path, status, created_at, batch_id, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                kind.value,
                source_path,
                JobStatus.IDLE.value,
                _utc_now_iso(),
                batch_id,
                pos,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    @_locked
    def add_jobs_to_batch(self, batch_id: int, source_paths: list[str]) -> list[int]:
        if self.get_batch(batch_id) is None:
            raise KeyError(batch_id)
        ids: list[int] = []
        for path in source_paths:
            ids.append(
                self.create_job(JobKind.FILE, path, batch_id=batch_id)
            )
        return ids

    @_locked
    def add_youtube_jobs_to_batch(self, batch_id: int, urls: list[str]) -> list[int]:
        if self.get_batch(batch_id) is None:
            raise KeyError(batch_id)
        ids: list[int] = []
        for url in urls:
            ids.append(
                self.create_job(JobKind.YOUTUBE, url, batch_id=batch_id)
            )
        return ids

    @_locked
    def recover_stale_state(self) -> int:
        """Reset jobs/batches left active after a crash or force-kill."""
        reset = 0
        for batch in self.list_batches():
            if batch["status"] in (
                BatchStatus.RUNNING.value,
                BatchStatus.PAUSED.value,
            ):
                self.update_batch(int(batch["id"]), status=BatchStatus.IDLE)
                reset += 1
        for job in self.list_jobs():
            if job["status"] in (
                JobStatus.QUEUED.value,
                JobStatus.RUNNING.value,
                JobStatus.FINALIZING.value,
            ):
                self.set_status(int(job["id"]), JobStatus.IDLE)
                self.set_progress(int(job["id"]), 0)
                reset += 1
        return reset

    @_locked
    def set_job_source_title(self, job_id: int, title: str | None) -> None:
        self._conn.execute(
            "UPDATE jobs SET source_title = ? WHERE id = ?",
            (title, job_id),
        )
        self._conn.commit()

    @_locked
    def set_job_archived(self, job_id: int, archived: bool) -> bool:
        if self.get_job(job_id) is None:
            return False
        self._conn.execute(
            "UPDATE jobs SET archived = ? WHERE id = ?",
            (1 if archived else 0, job_id),
        )
        self._conn.commit()
        return True

    @_locked
    def set_batch_archived(self, batch_id: int, archived: bool) -> bool:
        if self.get_batch(batch_id) is None:
            return False
        self._conn.execute(
            "UPDATE batches SET archived = ? WHERE id = ?",
            (1 if archived else 0, batch_id),
        )
        self._conn.commit()
        return True

    @_locked
    def set_status(self, job_id: int, status: JobStatus) -> None:
        now = _utc_now_iso()
        if status == JobStatus.RUNNING:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = COALESCE(started_at, ?), finished_at = NULL
                WHERE id = ?
                """,
                (status.value, now, job_id),
            )
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            self._conn.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = COALESCE(finished_at, ?)
                WHERE id = ?
                """,
                (status.value, now, job_id),
            )
        else:
            self._conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status.value, job_id),
            )
        self._conn.commit()

    @_locked
    def set_job_asr_snapshot(
        self, job_id: int, model_id: str, backend: str
    ) -> None:
        self._conn.execute(
            """
            UPDATE jobs SET asr_model_id = ?, asr_backend = ?
            WHERE id = ?
            """,
            (str(model_id or "").strip(), str(backend or "").strip(), job_id),
        )
        self._conn.commit()

    @_locked
    def begin_transcription(self, job_id: int, *, reset_progress: bool = True) -> None:
        now = _utc_now_iso()
        if reset_progress:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = ?, finished_at = NULL, progress = 0,
                    error_text = NULL, run_id = run_id + 1
                WHERE id = ?
                """,
                (JobStatus.QUEUED.value, now, job_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = ?, finished_at = NULL,
                    error_text = NULL, run_id = run_id + 1
                WHERE id = ?
                """,
                (JobStatus.QUEUED.value, now, job_id),
            )
        self._conn.commit()

    @_locked
    def set_last_export_path(self, job_id: int, path: str) -> None:
        self.set_last_export_paths(job_id, [path])

    @_locked
    def set_last_export_paths(self, job_id: int, paths: list[str]) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in paths:
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        last = normalized[-1] if normalized else None
        payload = json.dumps(normalized, ensure_ascii=False) if normalized else None
        self._conn.execute(
            """
            UPDATE jobs SET last_export_paths = ?, last_export_path = ?
            WHERE id = ?
            """,
            (payload, last, job_id),
        )
        self._conn.commit()

    @_locked
    def set_job_range(
        self,
        job_id: int,
        start_ms: int | None,
        end_ms: int | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET range_start_ms = ?, range_end_ms = ?
            WHERE id = ?
            """,
            (start_ms, end_ms, job_id),
        )
        self._conn.commit()

    @_locked
    def segments_revision(self, job_id: int) -> int:
        row = self._conn.execute(
            "SELECT segments_revision FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return int(row[0])

    @_locked
    def get_segments_snapshot(self, job_id: int) -> SegmentsSnapshot:
        job = self._conn.execute(
            "SELECT segments_revision FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise KeyError(job_id)
        seg_rows = self._conn.execute(
            """
            SELECT id, start_ms, end_ms, text, speaker
            FROM segments
            WHERE job_id = ?
            ORDER BY id
            """,
            (job_id,),
        ).fetchall()
        rows = tuple(
            SegmentSnapshotRow(
                row_id=int(r["id"]),
                start_ms=int(r["start_ms"]),
                end_ms=int(r["end_ms"]),
                text=str(r["text"]),
                speaker=r["speaker"],
            )
            for r in seg_rows
        )
        return SegmentsSnapshot(revision=int(job["segments_revision"]), rows=rows)

    @_locked
    def replace_segments(
        self,
        job_id: int,
        segments: list[Segment],
        *,
        expected_revision: int | None = None,
    ) -> int:
        if expected_revision is not None:
            current = self.segments_revision(job_id)
            if current != expected_revision:
                raise SegmentsRevisionConflictError(current)
        self._conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        self._conn.executemany(
            """
            INSERT INTO segments (job_id, start_ms, end_ms, text, speaker)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (job_id, seg.start_ms, seg.end_ms, seg.text, seg.speaker)
                for seg in segments
            ],
        )
        self._conn.execute(
            "UPDATE jobs SET segments_revision = segments_revision + 1 WHERE id = ?",
            (job_id,),
        )
        self._conn.commit()
        return self.segments_revision(job_id)

    @_locked
    def append_segments(self, job_id: int, segments: list[Segment]) -> None:
        if not segments:
            return
        self._conn.executemany(
            """
            INSERT INTO segments (job_id, start_ms, end_ms, text, speaker)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (job_id, seg.start_ms, seg.end_ms, seg.text, seg.speaker)
                for seg in segments
            ],
        )
        self._conn.execute(
            "UPDATE jobs SET segments_revision = segments_revision + 1 WHERE id = ?",
            (job_id,),
        )
        self._conn.commit()

    @_locked
    def upsert_speaker(self, job_id: int, speaker_key: str, display_name: str) -> None:
        self._conn.execute(
            """
            INSERT INTO speakers (job_id, speaker_key, display_name)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id, speaker_key) DO UPDATE SET display_name = excluded.display_name
            """,
            (job_id, speaker_key, display_name),
        )
        self._conn.commit()

    @_locked
    def list_speaker_names(self, job_id: int) -> dict[str, str]:
        rows = self._conn.execute(
            """
            SELECT speaker_key, display_name
            FROM speakers
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchall()
        return {
            str(row["speaker_key"]): str(row["display_name"])
            for row in rows
            if row["speaker_key"]
        }

    @_locked
    def apply_speaker_names(self, job_id: int) -> None:
        """Deprecated: overwrites segment keys with display names. Do not call."""
        self._conn.execute(
            """
            UPDATE segments
            SET speaker = (
                SELECT display_name FROM speakers
                WHERE speakers.job_id = segments.job_id
                  AND speakers.speaker_key = segments.speaker
            )
            WHERE job_id = ?
              AND speaker IN (
                SELECT speaker_key FROM speakers WHERE job_id = ?
              )
            """,
            (job_id, job_id),
        )
        self._conn.commit()

    @_locked
    def list_segments(self, job_id: int) -> list[Segment]:
        rows = self._conn.execute(
            """
            SELECT start_ms, end_ms, text, speaker
            FROM segments
            WHERE job_id = ?
            ORDER BY id
            """,
            (job_id,),
        ).fetchall()
        return [
            Segment(
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                text=row["text"],
                speaker=row["speaker"],
            )
            for row in rows
        ]

    @_locked
    def find_existing_transcripts(
        self,
        *,
        file_paths: list[str] | None = None,
        youtube_video_ids: list[str] | None = None,
    ) -> list[dict]:
        paths_in = [p for p in (file_paths or []) if (p or "").strip()]
        video_ids_in = [
            v.strip() for v in (youtube_video_ids or []) if (v or "").strip()
        ]
        if not paths_in and not video_ids_in:
            return []

        rows = self._conn.execute(
            """
            SELECT id, kind, source_path, source_title
            FROM jobs
            WHERE status = ? AND archived = 0
            """,
            (JobStatus.COMPLETED.value,),
        ).fetchall()

        file_map: dict[str, dict] = {}
        yt_map: dict[str, dict] = {}
        for row in rows:
            job = dict(row)
            kind = str(job.get("kind") or "")
            if kind == JobKind.FILE.value:
                key = _normalize_file_path_key(str(job["source_path"]))
                if key not in file_map:
                    file_map[key] = job
            elif kind == JobKind.YOUTUBE.value:
                video_id = extract_video_id(str(job["source_path"]))
                if video_id and video_id not in yt_map:
                    yt_map[video_id] = job

        matches: list[dict] = []
        for path in paths_in:
            key = _normalize_file_path_key(path)
            job = file_map.get(key)
            if not job:
                continue
            matches.append(
                {
                    "job_id": int(job["id"]),
                    "kind": JobKind.FILE.value,
                    "source_path": str(job["source_path"]),
                    "source_title": str(job.get("source_title") or ""),
                    "video_id": None,
                    "input_key": path,
                }
            )

        for video_id in video_ids_in:
            job = yt_map.get(video_id)
            if not job:
                continue
            matches.append(
                {
                    "job_id": int(job["id"]),
                    "kind": JobKind.YOUTUBE.value,
                    "source_path": str(job["source_path"]),
                    "source_title": str(job.get("source_title") or ""),
                    "video_id": video_id,
                    "input_key": video_id,
                }
            )

        return matches

    @_locked
    def list_jobs(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY id DESC"
        ).fetchall()
        return self._with_speaker_stats([dict(row) for row in rows])

    @_locked
    def get_job(self, job_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return self._with_speaker_stats([dict(row)])[0]

    @_locked
    def list_queued_jobs(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY id ASC",
            (JobStatus.QUEUED.value,),
        ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def set_error(self, job_id: int, text: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET error_text = ? WHERE id = ?",
            (text, job_id),
        )
        self._conn.commit()

    @_locked
    def set_progress(self, job_id: int, progress: float) -> None:
        self._conn.execute(
            "UPDATE jobs SET progress = ? WHERE id = ?",
            (progress, job_id),
        )
        self._conn.commit()

    @_locked
    def set_media_duration_s(self, job_id: int, seconds: float) -> None:
        self._conn.execute(
            "UPDATE jobs SET media_duration_s = ? WHERE id = ?",
            (float(seconds), job_id),
        )
        self._conn.commit()

    @_locked
    def delete_job(self, job_id: int) -> bool:
        if self.get_job(job_id) is None:
            return False
        self._conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        self._conn.execute("DELETE FROM speakers WHERE job_id = ?", (job_id,))
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self._conn.commit()
        return True
