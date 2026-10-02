from dataclasses import dataclass

from slysh.youtube_transcript_api import _segments_from_snippets


@dataclass
class FakeSnippet:
    text: str
    start: float
    duration: float


def test_segments_from_snippets_accepts_dict_rows():
    segments = _segments_from_snippets(
        [
            {"text": "Привет", "start": 1.5, "duration": 2.0},
            {"text": "", "start": 0.0, "duration": 1.0},
        ]
    )
    assert len(segments) == 1
    assert segments[0].text == "Привет"
    assert segments[0].start_ms == 1500
    assert segments[0].end_ms == 3500


def test_segments_from_snippets_accepts_api_objects():
    segments = _segments_from_snippets(
        [
            FakeSnippet(text="Hello", start=0.0, duration=1.2),
            FakeSnippet(text="World", start=1.2, duration=0.8),
        ]
    )
    assert len(segments) == 2
    assert segments[0].text == "Hello"
    assert segments[1].end_ms == 2000


def test_segments_from_snippets_uses_minimum_duration():
    segments = _segments_from_snippets(
        [{"text": "X", "start": 5.0, "duration": 0.0}],
    )
    assert len(segments) == 1
    assert segments[0].start_ms == 5000
    assert segments[0].end_ms == 6000
