from pathlib import Path

from slysh.youtube_ytdlp import _pick_audio_file, is_usable_audio_file


def test_pick_audio_file_prefers_wav(tmp_path):
    wav = tmp_path / "audio.wav"
    webm = tmp_path / "audio.webm"
    wav.write_bytes(b"wav" * 2048)
    webm.write_bytes(b"webm" * 2048)
    picked = _pick_audio_file(tmp_path)
    assert picked == wav


def test_pick_audio_file_ignores_ytdl_and_part(tmp_path):
    (tmp_path / "audio.mp4.part").write_bytes(b"x" * 10_000)
    (tmp_path / "audio.mp4.ytdl").write_bytes(b'{"downloader": "native"}')
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"wav" * 2048)
    assert _pick_audio_file(tmp_path) == wav


def test_is_usable_audio_file_rejects_sidecar(tmp_path):
    sidecar = tmp_path / "audio.mp4.ytdl"
    sidecar.write_bytes(b"meta")
    assert not is_usable_audio_file(sidecar)
