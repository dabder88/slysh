from pathlib import Path
import pytest
from slysh.models import Segment
from slysh.export import suggested_export_path, unique_export_path, write_output


def test_txt_paragraph_split_and_speaker_prefix(tmp_path: Path):
    segs = [
        Segment(start_ms=0, end_ms=1000, text="привет", speaker="Иван"),
        Segment(start_ms=4000, end_ms=5000, text="пока", speaker="Иван"),
    ]
    path = tmp_path / "out.txt"
    write_output(path, segs, "txt")
    text = path.read_text(encoding="utf-8")
    assert "Иван: привет" in text
    assert "\n\n" in text
    assert "Иван: пока" in text

def test_srt_uses_comma_millis(tmp_path: Path):
    segs = [Segment(start_ms=0, end_ms=1500, text="а", speaker=None)]
    path = tmp_path / "out.srt"
    write_output(path, segs, "srt")
    body = path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,500" in body
    assert "а" in body

def test_vtt_header_and_dot_millis(tmp_path: Path):
    segs = [Segment(start_ms=0, end_ms=1500, text="а", speaker=None)]
    path = tmp_path / "out.vtt"
    write_output(path, segs, "vtt")
    body = path.read_text(encoding="utf-8")
    assert body.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.500" in body


def test_suggested_export_path_uses_source_stem():
    path = suggested_export_path(r"F:\calls\Созвон 11.08.26.webm", "srt")
    assert path.name == "Созвон 11.08.26.srt"
    assert path.parent == Path(r"F:\calls")


def test_unique_export_path_avoids_collisions(tmp_path: Path):
    used: set[str] = set()
    first = unique_export_path(tmp_path, "call", "srt", used)
    second = unique_export_path(tmp_path, "call", "srt", used)
    assert first.name == "call.srt"
    assert second.name == "call_2.srt"


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="unknown format"):
        suggested_export_path(r"C:\a.wav", "docx")


def test_write_output_md_obsidian(tmp_path: Path):
    from slysh.export import write_job_export

    segs = [Segment(start_ms=0, end_ms=1500, text="hello", speaker="Ann")]
    path = tmp_path / "meeting.md"
    write_job_export(
        path,
        segs,
        "md",
        job={"source_path": r"F:\calls\meet.webm", "kind": "meeting"},
    )
    body = path.read_text(encoding="utf-8")
    assert body.startswith("---\n")
    assert 'title: "meet"' in body
    assert 'kind: "meeting"' in body
    assert "F:\\calls\\meet.webm" in body
    assert "## Transcript" in body
    assert "00:00:00.000" in body
    assert "Ann: hello" in body


def test_write_youtube_markdown_unified_format(tmp_path: Path):
    from slysh.export import write_job_export

    path = tmp_path / "video.md"
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    write_job_export(
        path,
        [Segment(0, 1000, "hello")],
        "md",
        youtube_meta={
            "title": 'Test "title"',
            "channel": "Ch",
            "url": url,
            "upload_date": "2024-01-01",
            "language": "ru",
        },
    )
    body = path.read_text(encoding="utf-8")
    assert body.startswith("---\n")
    assert "title: \"Test 'title'\"" in body
    assert f'source: "{url}"' in body
    assert 'kind: "youtube"' in body
    assert "## Transcript" in body
    assert "00:00:00.000" in body
    assert "hello" in body
    assert "Транскрипт" not in body
