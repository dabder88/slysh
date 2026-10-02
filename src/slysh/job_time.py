from __future__ import annotations

from datetime import datetime, timezone


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def job_duration_s(job: dict, now: datetime | None = None) -> float | None:
    start = _parse_iso(job.get("started_at"))
    if start is None:
        return None
    end = _parse_iso(job.get("finished_at"))
    if end is None:
        status = job.get("status")
        if status not in {"running", "queued", "finalizing"}:
            return None
        end = now or datetime.now(timezone.utc)
    return max(0.0, (end - start).total_seconds())
