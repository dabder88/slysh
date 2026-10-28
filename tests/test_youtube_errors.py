from slysh.youtube_errors import (
    format_youtube_failure,
    parse_subprocess_error_json,
)


def test_format_request_blocked():
    raw = """Traceback (most recent call last):
  File "x.py", line 1, in <module>
    raise RequestBlocked("blocked requests from your IP")
RequestBlocked: blocked requests from your IP"""
    out = format_youtube_failure(raw, method="ytdlp")
    assert out["code"] == "ip_blocked"
    assert "traceback" not in out["message"].lower()
    assert any("Apify" in h for h in out["hints"])


def test_format_geo_timeout_stderr():
    stderr = "ERROR: Unable to download video: HTTP Error 403: Forbidden"
    out = format_youtube_failure(stderr, method="ytdlp")
    assert out["code"] == "geo_or_network"
    assert any("прокси" in h.lower() or "Прокси" in h for h in out["hints"])


def test_format_wall_clock_timeout():
    out = format_youtube_failure(TimeoutError("wall-clock"), method="ytdlp")
    assert out["code"] == "timeout"


def test_parse_subprocess_error_json():
    stderr = "noise\n{\"error\": \"YouTube отклонил запрос с вашего IP.\"}\n"
    assert parse_subprocess_error_json(stderr) == "YouTube отклонил запрос с вашего IP."


def test_message_strips_traceback_block():
    raw = """Traceback (most recent call last):
  File "/tmp/x.py", line 99, in fetch
ValueError: bad"""
    out = format_youtube_failure(raw)
    assert 'File "' not in out["message"]
    assert "ValueError" in out["message"] or "bad" in out["message"]
