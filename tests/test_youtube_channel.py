import json
from unittest.mock import MagicMock

from slysh.youtube_channel import (
    YoutubeFeedFilters,
    dedupe_videos,
    expand_url_lines,
    expand_youtube_sources,
    list_feed_videos,
    resolve_start_video_id,
    YoutubeVideoRef,
)


def test_dedupe_videos():
    refs = [
        YoutubeVideoRef("a", "https://www.youtube.com/watch?v=a", "A"),
        YoutubeVideoRef("a", "https://www.youtube.com/watch?v=a", "A dup"),
        YoutubeVideoRef("b", "https://www.youtube.com/watch?v=b", "B"),
    ]
    out = dedupe_videos(refs)
    assert len(out) == 2
    assert out[0].video_id == "a"
    assert out[1].video_id == "b"


def test_expand_url_lines():
    refs = expand_url_lines(
        "https://youtu.be/dQw4w9WgXcQ\n# comment\n\nhttps://www.youtube.com/watch?v=abcdefghijk"
    )
    assert len(refs) == 2
    assert refs[0].video_id == "dQw4w9WgXcQ"
    assert refs[1].video_id == "abcdefghijk"


def test_list_feed_videos_flat(monkeypatch):
    lines = [
        json.dumps({"id": "vid1xxxxxxx", "title": "One", "url": "https://www.youtube.com/watch?v=vid1xxxxxxx"}),
        json.dumps({"id": "vid2xxxxxxx", "title": "Two", "url": "https://www.youtube.com/watch?v=vid2xxxxxxx"}),
    ]

    def fake_run(args, **kwargs):
        assert "--flat-playlist" in args
        assert "--match-filter" in args
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "\n".join(lines)
        proc.stderr = ""
        return proc

    monkeypatch.setattr("slysh.youtube_channel.find_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr("slysh.youtube_channel._run_ytdlp", fake_run)

    refs = list_feed_videos(
        "https://www.youtube.com/@test/videos",
        YoutubeFeedFilters(limit=10),
    )
    assert len(refs) == 2
    assert refs[0].title == "One"


def test_resolve_start_video_id_from_url():
    assert resolve_start_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert resolve_start_video_id("middlexxxxx") == "middlexxxxx"


def test_list_feed_start_video_older(monkeypatch):
    ids = ["newestxxxxx", "middlexxxxx", "oldestxxxxx"]
    lines = [
        json.dumps({"id": vid, "title": vid, "url": f"https://www.youtube.com/watch?v={vid}"})
        for vid in ids
    ]

    def fake_run(args, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "\n".join(lines)
        proc.stderr = ""
        return proc

    monkeypatch.setattr("slysh.youtube_channel.find_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr("slysh.youtube_channel._run_ytdlp", fake_run)

    refs = list_feed_videos(
        "https://www.youtube.com/@test/videos",
        YoutubeFeedFilters(
            start_video="https://www.youtube.com/watch?v=middlexxxxx",
            direction="older",
            limit=1,
        ),
    )
    assert len(refs) == 1
    assert refs[0].video_id == "middlexxxxx"


def test_expand_youtube_sources_lines_mode():
    refs = expand_youtube_sources(
        mode="lines",
        lines="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    assert len(refs) == 1
    assert refs[0].video_id == "dQw4w9WgXcQ"
