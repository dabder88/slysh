import json
from email.message import EmailMessage
from io import BytesIO
from urllib.error import HTTPError

import pytest

from slysh.engine_client import EngineError, transcribe_file


def test_transcribe_file_uses_error_json(monkeypatch):
    body = json.dumps({"error": "ffmpeg failed"}).encode("utf-8")

    def boom(*_args, **_kwargs):
        raise HTTPError(
            "http://127.0.0.1/transcribe_file",
            500,
            "Internal Server Error",
            hdrs=EmailMessage(),
            fp=BytesIO(body),
        )

    monkeypatch.setattr("slysh.engine_client.urlopen", boom)
    with pytest.raises(EngineError, match="ffmpeg"):
        transcribe_file("http://127.0.0.1:9", r"C:\созвон.webm")
