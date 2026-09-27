from __future__ import annotations

import re

from slysh.models import Segment
from slysh.timestamps import from_clock, to_clock

_LINE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\](?:\s+([^:\n]{1,40}):\s+)?(.*)$"
)


def format_transcript(segments: list[Segment]) -> str:
    lines: list[str] = []
    for segment in segments:
        clock = to_clock(segment.start_ms)
        body = (segment.text or "").strip()
        if segment.speaker:
            lines.append(f"[{clock}] {segment.speaker}: {body}")
        else:
            lines.append(f"[{clock}] {body}")
    return "\n".join(lines)


def parse_transcript(text: str) -> list[Segment]:
    parsed: list[Segment] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.match(line)
        if match is None:
            if parsed:
                prev = parsed[-1]
                parsed[-1] = Segment(
                    prev.start_ms,
                    prev.end_ms,
                    f"{prev.text} {line}".strip(),
                    prev.speaker,
                )
            continue
        clock, speaker, body = match.groups()
        start_ms = from_clock(clock)
        parsed.append(
            Segment(
                start_ms,
                start_ms + 1000,
                (body or "").strip(),
                speaker or None,
            )
        )
    for index, segment in enumerate(parsed):
        if index + 1 < len(parsed):
            end_ms = max(segment.start_ms + 1, parsed[index + 1].start_ms)
            parsed[index] = Segment(
                segment.start_ms,
                end_ms,
                segment.text,
                segment.speaker,
            )
    return parsed
