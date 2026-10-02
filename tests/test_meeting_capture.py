import importlib
import time
import types

import numpy as np
from fastapi.testclient import TestClient
from pathlib import Path

from slysh import api as api_mod
from slysh.api import create_ui_app
from slysh.chunking import SAMPLE_RATE
from slysh.db import Database
from slysh.models import Segment
from slysh.meeting_capture import (
    MAX_LAG_SAMPLES,
    MeetingMixer,
    list_input_devices,
    list_output_devices,
    loopback_supported,
    mix_frames,
    resample_to_16k,
    resolve_loopback_device,
    to_mono,
)
from slysh.speakers import FakeSpeakersBackend
import slysh.meeting_capture as meeting_capture


def _patch_msdd(monkeypatch, backend_cls):
    from slysh import engine_client

    def fake_ensure(app):
        return "http://engine.test"

    def fake_label(base_url, path, segments):
        labeled = backend_cls().label(path, segments)
        return {
            "segments": [
                {
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "text": s.text,
                    "speaker": s.speaker,
                }
                for s in labeled
            ]
        }

    monkeypatch.setattr(api_mod, "_ensure_engine_url", fake_ensure)
    monkeypatch.setattr(engine_client, "label_speakers", fake_label)


def _wait_speakers(client, job_id: int) -> dict:
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if not job.get("speakers_running"):
            return job
        time.sleep(0.05)
    assert job is not None
    return job


class _FakeCapture:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.paused = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def test_to_mono_averages_channels():
    stereo = np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32)
    mono = to_mono(stereo)
    assert mono.shape == (2,)
    assert abs(float(mono[0]) - 0.0) < 1e-6
    assert abs(float(mono[1]) - 0.5) < 1e-6


def test_resample_48k_to_16k_length():
    src = np.ones(48000, dtype=np.float32)
    out = resample_to_16k(src, 48000)
    assert abs(len(out) - SAMPLE_RATE) <= 1
    assert abs(float(np.mean(out)) - 1.0) < 1e-3


def test_mix_frames_clips_and_pads_silence():
    silent = mix_frames(np.zeros(4, np.float32), np.zeros(4, np.float32))
    assert silent.shape == (4,)
    assert np.allclose(silent, 0)
    clipped = mix_frames(np.ones(2, np.float32) * 0.8, np.ones(2, np.float32) * 0.8)
    assert np.all(clipped <= 1.0)
    padded = mix_frames(np.array([0.5], np.float32), np.array([0.0, 0.2], np.float32))
    assert padded.shape == (2,)
    assert abs(float(padded[0]) - 0.5) < 1e-6


def test_mixer_system_only_passes_through():
    mixer = MeetingMixer(include_mic=False)
    mixer.push_system(np.ones(8, np.float32) * 0.25)
    out = mixer.take_mixed()
    assert np.allclose(out, 0.25)


def test_mixer_pads_when_system_leads():
    mixer = MeetingMixer(include_mic=True)
    mixer.push_system(np.ones(MAX_LAG_SAMPLES + 16, np.float32) * 0.5)
    mixed = mixer.take_mixed()
    assert len(mixed) == 16
    assert np.allclose(mixed, 0.5)


def _patch_audio_devices(monkeypatch):
    hostapis = [
        {"name": "MME", "default_input_device": 0, "default_output_device": 1},
        {"name": "Windows WASAPI", "default_input_device": 4, "default_output_device": 5},
    ]
    devices = [
        {
            "name": "Microsoft Sound Mapper - Input",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
            "default_samplerate": 44100,
        },
        {
            "name": "Microsoft Sound Mapper - Output",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
            "default_samplerate": 44100,
        },
        {
            "name": "Speakers (Realtek)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
            "default_samplerate": 48000,
        },
        {
            "name": "Headset (BT Hands-Free)",
            "max_input_channels": 1,
            "max_output_channels": 1,
            "hostapi": 0,
            "default_samplerate": 16000,
        },
        {
            "name": "Microphone (Realtek)",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 1,
            "default_samplerate": 48000,
        },
        {
            "name": "Headphones (BT Stereo)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 1,
            "default_samplerate": 48000,
        },
        {
            "name": "Speakers (Realtek)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 1,
            "default_samplerate": 48000,
        },
        {
            "name": "Headset (WH-1000XM5 Hands-Free)",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "hostapi": 1,
            "default_samplerate": 16000,
        },
    ]

    def query_devices(index=None):
        if index is None:
            return devices
        return devices[index]

    def query_hostapis(index=None):
        if index is None:
            return hostapis
        return hostapis[index]

    monkeypatch.setattr(meeting_capture, "_com_render_outputs", lambda: [])
    monkeypatch.setattr(meeting_capture.sd, "query_devices", query_devices)
    monkeypatch.setattr(meeting_capture.sd, "query_hostapis", query_hostapis)
    return devices


def test_lists_wasapi_headphones_and_skips_mapper(monkeypatch):
    _patch_audio_devices(monkeypatch)
    outputs = list_output_devices()
    names = [item["name"] for item in outputs]
    assert "Microsoft Sound Mapper - Output" not in names
    assert "Headphones (BT Stereo)" in names
    assert outputs[0]["name"] == "Headphones (BT Stereo)"
    assert names.count("Speakers (Realtek)") == 1

    inputs = list_input_devices(probe=lambda _index: True)
    in_names = [item["name"] for item in inputs]
    assert "Microsoft Sound Mapper - Input" not in in_names
    assert "Microphone (Realtek)" in in_names
    assert "Headset (WH-1000XM5 Hands-Free)" in in_names
    assert "Headset (BT Hands-Free)" not in in_names


def test_resolve_loopback_maps_mapper_and_mme_to_wasapi(monkeypatch):
    _patch_audio_devices(monkeypatch)
    assert resolve_loopback_device(1) == 5
    assert resolve_loopback_device(2) == 6
    assert resolve_loopback_device(5) == 5


def test_meeting_start_without_outputs_returns_400(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [])
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/meeting/start", json={"include_mic": False})
    assert r.status_code == 400
    assert "выход" in r.json()["detail"].lower()


def test_meeting_start_creates_job_and_wav(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 3, "name": "Speakers"}])
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/meeting/start", json={"include_mic": True, "output_device_id": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "meeting"
    assert Path(body["source_path"]).exists()
    assert Path(body["source_path"]).name.startswith("meeting-")
    status = client.get("/api/meeting/status").json()
    assert status["listening"] is True
    assert status["session_active"] is True
    assert status["paused"] is False
    assert status["job_id"] == body["id"]
    devices = client.get("/api/meeting/devices").json()
    assert devices["outputs"][0]["id"] == 3
    stopped = client.post("/api/meeting/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "completed"
    assert stopped.json()["kind"] == "meeting"


def test_meeting_conflicts_with_live(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])

    class _FakeStream:
        def start(self):
            return None

        def stop(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(api_mod.sd, "InputStream", lambda **kwargs: _FakeStream())
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 1, "name": "Out"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)

    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    live = client.post("/api/live/start", json={})
    assert live.status_code == 200
    blocked = client.post("/api/meeting/start", json={"include_mic": False})
    assert blocked.status_code == 400
    assert "диктофон" in blocked.json()["detail"].lower()
    client.post("/api/live/stop")
    ok = client.post("/api/meeting/start", json={"include_mic": False})
    assert ok.status_code == 200
    blocked_live = client.post("/api/live/start", json={})
    assert blocked_live.status_code == 400
    client.post("/api/meeting/stop")


def test_meeting_pause_resume_preserves_segments(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 3, "name": "Speakers"}])
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    started = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    assert started.status_code == 200
    job_id = started.json()["id"]
    db.replace_segments(job_id, [Segment(0, 1000, "первая фраза")])
    paused = client.post("/api/meeting/pause")
    assert paused.status_code == 200
    body = paused.json()
    assert body["paused"] is True
    assert body["session_active"] is True
    assert body["listening"] is False
    assert body["segments"][0]["text"] == "первая фраза"
    resumed = client.post("/api/meeting/resume")
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False
    assert resumed.json()["listening"] is True
    assert resumed.json()["segments"][0]["text"] == "первая фраза"
    client.post("/api/meeting/stop")


def test_meeting_pause_requires_active_session(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post("/api/meeting/pause")
    assert r.status_code == 400


def test_meeting_capture_pause_skips_session_push(tmp_path):
    from slysh.live_buffer import LiveSession
    from slysh.meeting_capture import MeetingCapture

    wav = tmp_path / "meeting.wav"
    session = LiveSession(wav_path=wav)
    holder = {"rms_mic": 0.0, "rms_system": 0.0}
    capture = MeetingCapture(
        session=session,
        output_device_id=None,
        mic_device_id=None,
        include_mic=False,
        rms_holder=holder,
    )
    capture._sys_rate = 16000
    capture.pause()
    capture._on_wasapi_system(np.ones(1600, dtype=np.float32))
    assert session.buffered_samples() == 0
    capture.resume()
    capture._on_wasapi_system(np.ones(1600, dtype=np.float32))
    import time

    for _ in range(50):
        if session.buffered_samples() > 0:
            break
        time.sleep(0.01)
    assert session.buffered_samples() > 0
    capture.stop()
    session.flush()


def test_loopback_supported_is_win32_only(monkeypatch):
    monkeypatch.setattr(meeting_capture.sys, "platform", "win32")
    assert meeting_capture.loopback_supported() is True
    monkeypatch.setattr(meeting_capture.sys, "platform", "linux")
    assert meeting_capture.loopback_supported() is False


def test_meeting_devices_refresh_reinits_and_skips_mic_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    calls = {"refresh": 0, "mics": 0}
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(
        api_mod,
        "list_output_devices",
        lambda: [{"id": "{guid}", "name": "Headphones"}],
    )

    def fake_refresh():
        calls["refresh"] += 1

    def fake_mics(app=None, force=False):
        calls["mics"] += 1
        assert force is True
        return [{"id": 4, "name": "BT Mic"}]

    monkeypatch.setattr(api_mod, "refresh_audio_devices", fake_refresh)
    monkeypatch.setattr(api_mod, "_list_input_mics", fake_mics)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    body = client.get("/api/meeting/devices?refresh=1").json()
    assert calls["refresh"] == 1
    assert calls["mics"] == 1
    assert body["outputs"][0]["name"] == "Headphones"
    assert body["mics"][0]["name"] == "BT Mic"
    assert body["loopback_supported"] is True


def test_meeting_start_accepts_string_output_id(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(
        api_mod,
        "list_output_devices",
        lambda: [{"id": "{0.0.0.00000000}.{abcd}", "name": "Speakers"}],
    )
    monkeypatch.setattr(
        api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}]
    )
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    r = client.post(
        "/api/meeting/start",
        json={"include_mic": False, "output_device_id": "{0.0.0.00000000}.{abcd}"},
    )
    assert r.status_code == 200
    client.post("/api/meeting/stop")


def test_meeting_stop_then_speakers(tmp_path, monkeypatch):
    _patch_msdd(monkeypatch, FakeSpeakersBackend)
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 3, "name": "Speakers"}])
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    started = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    assert started.status_code == 200
    job_id = started.json()["id"]
    db.replace_segments(job_id, [Segment(0, 1000, "привет"), Segment(1200, 2000, "алло")])
    stopped = client.post("/api/meeting/stop")
    assert stopped.status_code == 200
    assert stopped.json()["kind"] == "meeting"
    assert stopped.json()["status"] == "completed"
    r = client.post(f"/api/jobs/{job_id}/speakers")
    assert r.status_code == 200
    job = _wait_speakers(client, job_id)
    assert not job.get("speakers_error")
    segs = db.list_segments(job_id)
    assert segs[0].speaker == "SPEAKER_00"
    assert job.get("has_speakers") is True


def test_meeting_clear_resets_screen_job_id(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(api_mod, "loopback_supported", lambda: True)
    monkeypatch.setattr(api_mod, "list_output_devices", lambda: [{"id": 3, "name": "Speakers"}])
    monkeypatch.setattr(api_mod, "_list_input_mics", lambda app=None, force=False: [{"id": 0, "name": "Mic"}])
    monkeypatch.setattr(api_mod, "MeetingCapture", _FakeCapture)
    db = Database(tmp_path / "app.db")
    app = create_ui_app(db=db, engine=None, auto_start_engine=False)
    client = TestClient(app)
    started = client.post("/api/meeting/start", json={"include_mic": False, "output_device_id": 3})
    job_id = started.json()["id"]
    db.replace_segments(job_id, [Segment(0, 1000, "привет")])
    client.post("/api/meeting/stop")
    assert client.get("/api/meeting/status").json()["job_id"] == job_id
    cleared = client.post("/api/meeting/clear")
    assert cleared.status_code == 200
    status = client.get("/api/meeting/status").json()
    assert status["job_id"] is None
    assert "segments" not in status
    blocked = client.post("/api/meeting/clear")
    assert blocked.status_code == 200
