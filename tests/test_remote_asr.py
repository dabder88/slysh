import io
import json
import subprocess
import time
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from slysh.api import create_ui_app
from slysh.compute import write_asr_env
from slysh.db import Database
from slysh.gemini_cli import parse_gemini_output
from slysh.models import JobKind, Segment
from slysh.providers import (
    mask_secret,
    normalize_stt_endpoint,
    save_http_preset,
    save_openrouter,
    upsert_custom_provider,
)
from slysh.remote_asr import (
    gladia_init_payload,
    parse_deepgram_payload,
    parse_gladia_payload,
    parse_transcription_payload,
    transcribe_http_file,
    _error_body,
)


def _fake_transcribe_media(segments: list[Segment]):
    def fake(**kwargs):
        on_segments = kwargs.get("on_segments")
        if on_segments and segments:
            on_segments(list(segments))
        return list(segments)

    return fake


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GIGAAM_DESKTOP_HOME", str(home))
    monkeypatch.setenv("GIGAAM_PROJECT_MODELS", str(tmp_path / "models"))
    (tmp_path / "models").mkdir()
    monkeypatch.delenv("GIGAAM_ASR_ID", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GLADIA_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setattr("slysh.providers.find_gemini_binary", lambda which=None: None)
    return home


def test_normalize_stt_endpoint_appends_path():
    assert (
        normalize_stt_endpoint("https://api.groq.com/openai/v1")
        == "https://api.groq.com/openai/v1/audio/transcriptions"
    )
    assert (
        normalize_stt_endpoint("https://host/v1/audio/transcriptions")
        == "https://host/v1/audio/transcriptions"
    )


def test_mask_secret_hides_body():
    assert mask_secret("sk-secret-key") == "…-key"
    assert "secret" not in mask_secret("sk-secret-key")


def test_parse_verbose_json_seconds():
    segs = parse_transcription_payload(
        {
            "text": "hello",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "hello"},
                {"start": 1.5, "end": 2.0, "text": "world"},
            ],
        },
        2000,
    )
    assert [s.text for s in segs] == ["hello", "world"]
    assert segs[0].end_ms == 1500
    assert segs[1].start_ms == 1500


def test_parse_plain_text_fallback():
    segs = parse_transcription_payload({"text": "одно"}, 3400)
    assert len(segs) == 1
    assert segs[0].text == "одно"
    assert segs[0].end_ms == 3400


def test_parse_gemini_wrapped_json():
    raw = json.dumps({"response": json.dumps({"text": "раз два"})})
    segs = parse_gemini_output(raw, 1000)
    assert segs[0].text == "раз два"


def test_write_asr_env_remote_backend():
    env = {}
    write_asr_env(env, "openrouter:openai/whisper-1", None)
    assert env["GIGAAM_ASR_BACKEND"] == "remote"


def test_providers_return_key_in_api(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    put = client.put(
        "/api/providers/openrouter",
        json={"api_key": "sk-secret-value"},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["openrouter"]["api_key_set"] is True
    assert body["openrouter"]["api_key"] == "sk-secret-value"


def test_custom_provider_crud(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    added = client.post(
        "/api/providers/custom",
        json={
            "name": "Groq",
            "endpoint": "https://api.groq.com/openai/v1",
            "model": "whisper-large-v3-turbo",
            "api_key": "gsk-hidden",
        },
    )
    assert added.status_code == 200
    row = added.json()["custom"][0]
    assert row["endpoint"].startswith("https://")
    assert added.json()["custom"][0]["api_key"] == "gsk-hidden"
    models = client.get("/api/models").json()
    ids = [item["id"] for item in models["items"]]
    assert any(i.startswith("custom:") for i in ids)
    deleted = client.delete(f"/api/providers/custom/{row['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["custom"] == []


def test_models_include_openrouter_without_local_weights(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    data = client.get("/api/models").json()
    ids = [item["id"] for item in data["items"]]
    assert any(i.startswith("openrouter:") for i in ids)
    assert "cli:gemini" in ids


def test_http_stt_parses_fake_urlopen(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_openrouter(api_key="sk-test")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    seen = {}

    class Resp:
        def read(self):
            return json.dumps(
                {"text": "ok", "segments": [{"start": 0, "end": 1, "text": "ok"}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        return Resp()

    segs = transcribe_http_file(
        backend="openrouter",
        model_id="openrouter:openai/whisper-1",
        audio_path=str(audio),
        duration_ms=1000,
        opener=opener,
    )
    assert segs[0].text == "ok"
    assert "openrouter.ai" in seen["url"]


def test_http_stt_retries_without_verbose_json(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_openrouter(api_key="sk-test")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    calls = {"n": 0}

    class Resp:
        def read(self):
            return json.dumps({"text": "plain"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(
                req.full_url,
                400,
                "bad verbose",
                None,
                io.BytesIO(b'{"error":"no verbose"}'),
            )
        return Resp()

    segs = transcribe_http_file(
        backend="openrouter",
        model_id="openrouter:openai/whisper-1",
        audio_path=str(audio),
        duration_ms=500,
        opener=opener,
    )
    assert segs[0].text == "plain"
    assert calls["n"] == 2


def test_gemini_runner_gets_at_path(tmp_path, monkeypatch):
    from slysh.gemini_cli import transcribe_gemini_file

    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")
    seen = {}

    class Proc:
        returncode = 0
        stdout = json.dumps({"text": "cli"})
        stderr = ""

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        return Proc()

    segs = transcribe_gemini_file(
        str(audio),
        duration_ms=1000,
        runner=runner,
        binary="gemini.exe",
    )
    assert segs[0].text == "cli"
    prompt = seen["cmd"][2]
    assert "@" in prompt
    assert str(audio.resolve()) in prompt


def test_openrouter_job_does_not_spawn_engine(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_openrouter(api_key="sk-test")
    monkeypatch.setenv("GIGAAM_ASR_ID", "openrouter:openai/whisper-1")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    spawned = {"n": 0}

    def fake_popen(*args, **kwargs):
        spawned["n"] += 1
        raise AssertionError("engine must not start for OpenRouter")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "slysh.api.transcribe_media",
        _fake_transcribe_media([Segment(0, 800, "облако")]),
    )
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db, engine=None, auto_start_engine=True))
    r = client.post(f"/api/jobs/{job_id}/start")
    assert r.status_code == 200
    status = None
    for _ in range(80):
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert spawned["n"] == 0
    assert status == "completed"
    segs = client.get(f"/api/jobs/{job_id}").json()["segments"]
    assert segs[0]["text"] == "облако"


def test_custom_job_uses_saved_endpoint(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    row = upsert_custom_provider(
        provider_id="local-fw",
        name="Local",
        endpoint="http://127.0.0.1:9000/v1",
        model="whisper-1",
        api_key="",
    )
    monkeypatch.setenv("GIGAAM_ASR_ID", f"custom:{row['id']}")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    seen = {}

    def fake_media(**kwargs):
        seen.update(kwargs)
        return [Segment(0, 100, "ok")]

    monkeypatch.setattr("slysh.api.transcribe_media", fake_media)
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db, engine=None, auto_start_engine=True))
    client.post(f"/api/jobs/{job_id}/start")
    for _ in range(80):
        if client.get(f"/api/jobs/{job_id}").json()["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert seen["backend"] == "custom"
    assert seen["model_id"] == "custom:local-fw"


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_write_asr_env_http_backend():
    env = {}
    write_asr_env(env, "http:groq", None)
    assert env["GIGAAM_ASR_BACKEND"] == "remote"


def test_http_presets_listed_and_groq_key_masked(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    listed = client.get("/api/providers").json()
    ids = [row["id"] for row in listed["http"]]
    assert ids == ["groq", "openai", "gladia", "deepgram"]
    put = client.post("/api/providers/http/groq", json={"api_key": "gsk-secret-value"})
    assert put.status_code == 200
    dumped = json.dumps(put.json())
    assert "gsk-secret-value" not in dumped
    groq = next(row for row in put.json()["http"] if row["id"] == "groq")
    assert groq["api_key_set"] is True
    assert groq["ready"] is True
    models = client.get("/api/models").json()
    item = next(row for row in models["items"] if row["id"] == "http:groq")
    assert item["ready"] is True
    assert item["backend"] == "http"


def test_http_preset_unknown_404(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    client = TestClient(create_ui_app(Database(tmp_path / "app.db"), engine=None))
    r = client.put("/api/providers/http/unknown", json={"api_key": "x"})
    assert r.status_code == 404


def test_gladia_init_payload_skips_solaria_3():
    assert gladia_init_payload("https://api.gladia.io/file/x", "solaria-3") == {
        "audio_url": "https://api.gladia.io/file/x"
    }
    assert gladia_init_payload("https://api.gladia.io/file/x", "solaria-1")["model"] == "solaria-1"


def test_error_body_includes_gladia_validation():
    exc = HTTPError(
        "https://api.gladia.io/v2/pre-recorded",
        400,
        "bad",
        None,
        io.BytesIO(
            json.dumps(
                {
                    "message": "Invalid parameter(s). See validation_errors for more details.",
                    "validation_errors": ['Field "model" is invalid'],
                }
            ).encode()
        ),
    )
    text = _error_body(exc)
    assert "Invalid parameter" in text
    assert "model" in text


def test_parse_gladia_utterances():
    segs = parse_gladia_payload(
        {
            "status": "done",
            "result": {
                "transcription": {
                    "full_transcript": "привет мир",
                    "utterances": [
                        {"start": 0.0, "end": 0.8, "text": "привет"},
                        {"start": 0.8, "end": 1.5, "text": "мир"},
                    ],
                }
            },
        },
        2000,
    )
    assert [s.text for s in segs] == ["привет", "мир"]
    assert segs[1].start_ms == 800


def test_parse_deepgram_utterances():
    segs = parse_deepgram_payload(
        {
            "results": {
                "utterances": [
                    {"start": 0.0, "end": 1.0, "transcript": "one"},
                    {"start": 1.0, "end": 2.0, "transcript": "two"},
                ]
            }
        },
        2000,
    )
    assert [s.text for s in segs] == ["one", "two"]


def test_groq_uses_openai_transcriptions(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_http_preset("groq", api_key="gsk-test")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _JsonResp({"text": "ok", "segments": [{"start": 0, "end": 1, "text": "ok"}]})

    segs = transcribe_http_file(
        backend="http",
        model_id="http:groq",
        audio_path=str(audio),
        duration_ms=1000,
        opener=opener,
    )
    assert segs[0].text == "ok"
    assert seen["url"].endswith("/audio/transcriptions")
    assert "api.groq.com" in seen["url"]
    assert seen["auth"] == "Bearer gsk-test"


def test_gladia_upload_then_poll(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_http_preset("gladia", api_key="glad-key", model="solaria-3")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    seen = {"urls": []}
    monkeypatch.setattr("slysh.remote_asr.time.sleep", lambda *_args, **_kwargs: None)

    def opener(req, timeout=None):
        url = req.full_url
        method = req.get_method()
        seen["urls"].append((method, url))
        key = req.get_header("X-gladia-key") or req.get_header("x-gladia-key")
        assert key == "glad-key"
        assert req.get_header("Authorization") in (None, "")
        if url.endswith("/v2/upload"):
            body = req.data or b""
            assert b'name="audio"' in body
            return _JsonResp({"audio_url": "https://api.gladia.io/file/abc"})
        if method == "POST" and url.endswith("/v2/pre-recorded"):
            seen["init"] = json.loads((req.data or b"{}").decode())
            return _JsonResp(
                {
                    "id": "job-1",
                    "result_url": "https://api.gladia.io/v2/pre-recorded/job-1",
                }
            )
        return _JsonResp(
            {
                "status": "done",
                "result": {
                    "transcription": {
                        "full_transcript": "привет",
                        "utterances": [{"start": 0, "end": 1.2, "text": "привет"}],
                    }
                },
            }
        )

    segs = transcribe_http_file(
        backend="http",
        model_id="http:gladia",
        audio_path=str(audio),
        duration_ms=1200,
        opener=opener,
    )
    assert segs[0].text == "привет"
    assert segs[0].end_ms == 1200
    assert seen["init"]["audio_url"] == "https://api.gladia.io/file/abc"
    assert "model" not in seen["init"]
    assert any(url.endswith("/v2/upload") for _method, url in seen["urls"])
    assert any("/v2/pre-recorded" in url for _method, url in seen["urls"])


def test_deepgram_listen_token_header(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_http_preset("deepgram", api_key="dg-key")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _JsonResp(
            {
                "results": {
                    "utterances": [{"start": 0, "end": 0.5, "transcript": "hello"}]
                }
            }
        )

    segs = transcribe_http_file(
        backend="http",
        model_id="http:deepgram",
        audio_path=str(audio),
        duration_ms=500,
        opener=opener,
    )
    assert segs[0].text == "hello"
    assert "/v1/listen" in seen["url"]
    assert "model=nova-3" in seen["url"]
    assert seen["auth"] == "Token dg-key"


def test_custom_gladia_protocol(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    row = upsert_custom_provider(
        provider_id="my-gladia",
        name="Gladia EU",
        endpoint="https://api.gladia.io",
        model="solaria-1",
        api_key="glad-custom",
        protocol="gladia",
    )
    assert row["protocol"] == "gladia"
    assert row["ready"] is True
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"mp3")
    monkeypatch.setattr("slysh.remote_asr.time.sleep", lambda *_args, **_kwargs: None)

    def opener(req, timeout=None):
        if req.full_url.endswith("/v2/upload"):
            return _JsonResp({"audio_url": "https://api.gladia.io/file/x"})
        if req.get_method() == "POST":
            return _JsonResp({"id": "1", "result_url": "https://api.gladia.io/v2/pre-recorded/1"})
        return _JsonResp(
            {
                "status": "done",
                "result": {"transcription": {"full_transcript": "ok"}},
            }
        )

    segs = transcribe_http_file(
        backend="custom",
        model_id="custom:my-gladia",
        audio_path=str(audio),
        duration_ms=800,
        opener=opener,
    )
    assert segs[0].text == "ok"


def test_gladia_job_does_not_spawn_engine(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    save_http_preset("gladia", api_key="glad-key")
    monkeypatch.setenv("GIGAAM_ASR_ID", "http:gladia")
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    spawned = {"n": 0}

    def fake_popen(*args, **kwargs):
        spawned["n"] += 1
        raise AssertionError("engine must not start for Gladia")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "slysh.api.transcribe_media",
        _fake_transcribe_media([Segment(0, 800, "гладиа")]),
    )
    db = Database(tmp_path / "app.db")
    job_id = db.create_job(JobKind.FILE, str(wav))
    client = TestClient(create_ui_app(db, engine=None, auto_start_engine=True))
    r = client.post(f"/api/jobs/{job_id}/start")
    assert r.status_code == 200
    status = None
    for _ in range(80):
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert spawned["n"] == 0
    assert status == "completed"
    assert client.get(f"/api/jobs/{job_id}").json()["segments"][0]["text"] == "гладиа"
