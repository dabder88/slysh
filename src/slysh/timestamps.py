def to_timestamp(ms: float, ms_separator: str = ".") -> str:
    ms = int(ms)
    hr = ms // 3_600_000
    ms -= hr * 3_600_000
    mins = ms // 60_000
    ms -= mins * 60_000
    secs = ms // 1000
    millis = ms - secs * 1000
    return f"{hr:02}:{mins:02}:{secs:02}{ms_separator}{millis:03}"


def to_clock(ms: float) -> str:
    ms = max(0, int(ms))
    hr = ms // 3_600_000
    ms -= hr * 3_600_000
    mins = ms // 60_000
    ms -= mins * 60_000
    secs = ms // 1000
    return f"{hr:02}:{mins:02}:{secs:02}"


def from_clock(text: str) -> int:
    parts = (text or "").strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"bad clock: {text}")
    hours, minutes, seconds = (int(part) for part in parts)
    return ((hours * 3600) + (minutes * 60) + seconds) * 1000
