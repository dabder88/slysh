from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class JobKind(str, Enum):
    FILE = "file"
    LIVE = "live"
    MEETING = "meeting"
    YOUTUBE = "youtube"

class JobStatus(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"

@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None

    def export_text(self) -> str:
        body = self.text.strip()
        if self.speaker:
            return f"{self.speaker}: {body}"
        return body
