from slysh.models import Segment
from slysh.vtt import merge_segments, parse_vtt


def test_merge_segments_groups_short_cues():
    segments = [
        Segment(0, 2000, "Первая"),
        Segment(2000, 4000, "вторая"),
        Segment(4000, 6000, "третья"),
        Segment(6000, 8000, "четвёртая"),
    ]
    merged = merge_segments(segments, target_ms=8000, max_gap_ms=500)
    assert len(merged) == 1
    assert merged[0].start_ms == 0
    assert merged[0].end_ms == 8000
    assert "четвёртая" in merged[0].text


def test_merge_segments_respects_pause_gap():
    segments = [
        Segment(0, 2000, "До паузы"),
        Segment(8000, 10000, "После паузы"),
    ]
    merged = merge_segments(segments, target_ms=20000, max_gap_ms=1500)
    assert len(merged) == 2


def test_parse_vtt_basic():
    text = """WEBVTT

00:00:01.000 --> 00:00:03.500
Первая <c>реплика</c>

00:00:04.000 --> 00:00:06.000
Вторая реплика
"""
    segments = parse_vtt(text)
    assert len(segments) == 2
    assert segments[0].start_ms == 1000
    assert segments[0].end_ms == 3500
    assert segments[0].text == "Первая реплика"
    assert segments[1].text == "Вторая реплика"


def test_parse_vtt_short_timestamp():
    text = """WEBVTT

00:01.000 --> 00:03.000
Короткий таймкод
"""
    segments = parse_vtt(text)
    assert len(segments) == 1
    assert segments[0].start_ms == 1000
    assert segments[0].end_ms == 3000
