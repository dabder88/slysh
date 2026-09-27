from slysh.models import Segment
from slysh.transcript import format_transcript, parse_transcript


def test_format_and_parse_roundtrip():
    original = [
        Segment(0, 20000, "привет", speaker=None),
        Segment(20000, 40000, "пока", speaker="Иван"),
    ]
    text = format_transcript(original)
    assert "[00:00:00] привет" in text
    assert "[00:00:20] Иван: пока" in text
    parsed = parse_transcript(text)
    assert parsed[0].text == "привет"
    assert parsed[0].start_ms == 0
    assert parsed[1].speaker == "Иван"
    assert parsed[1].start_ms == 20000
    assert parsed[0].end_ms == 20000
