from unittest import mock

from slysh.youtube_ytdlp import YTDLP_CALL_TIMEOUT, _download_subtitles


def test_download_subtitles_passes_call_timeout(monkeypatch):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        proc = mock.Mock()
        proc.returncode = 1
        proc.stderr = "fail"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("slysh.youtube_ytdlp._run_ytdlp", fake_run)
    _download_subtitles(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "ru",
        "/tmp/%(id)s",
        cookie_mode="none",
        extractor_args="youtube:player_client=android_vr",
        all_langs=False,
    )
    assert captured["timeout"] == YTDLP_CALL_TIMEOUT
