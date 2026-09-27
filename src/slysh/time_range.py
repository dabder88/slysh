from __future__ import annotations


def normalize_range(
    start_ms: int | None,
    end_ms: int | None,
) -> tuple[int | None, int | None]:
    start = None if start_ms is None else int(start_ms)
    end = None if end_ms is None else int(end_ms)
    if start is not None and start < 0:
        raise ValueError("Начало интервала не может быть меньше нуля.")
    if end is not None and end < 0:
        raise ValueError("Конец интервала не может быть меньше нуля.")
    if start is not None and end is not None and end <= start:
        raise ValueError("Конец интервала должен быть позже начала.")
    return start, end
