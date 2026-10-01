"""Speaker labeling via engine HTTP (keeps NeMo/torch out of UI process)."""
from __future__ import annotations

from collections.abc import Callable

from slysh import engine_client
from slysh.engine_client import EngineError
from slysh.models import Segment
from slysh.speakers import SpeakerCancelledError


class EngineSpeakersBackend:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def label(
        self,
        source_path: str,
        segments: list[Segment],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Segment]:
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        try:
            payload = engine_client.label_speakers(
                self._base_url,
                source_path,
                segments,
            )
        except EngineError as exc:
            if "cancelled" in str(exc).lower():
                raise SpeakerCancelledError() from exc
            raise
        if cancelled and cancelled():
            raise SpeakerCancelledError()
        out: list[Segment] = []
        for row in payload.get("segments") or []:
            if not isinstance(row, dict):
                continue
            out.append(
                Segment(
                    int(row["start_ms"]),
                    int(row["end_ms"]),
                    str(row.get("text") or ""),
                    speaker=row.get("speaker"),
                )
            )
        return out
