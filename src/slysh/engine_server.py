from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
from typing import Callable

import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from slysh.decode import DecodeError
from slysh.models import Segment
from slysh.transcribe import FilePipeline


class TranscribeFileBody(BaseModel):
    path: str
    start_ms: int | None = None
    end_ms: int | None = None


class TranscribeChunkBody(BaseModel):
    samples: list[float]


def _segments_payload(segments: list[Segment]) -> dict:
    return {
        "segments": [
            {
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text": s.text,
                "speaker": s.speaker,
            }
            for s in segments
        ]
    }


class _CliFakeBackend:
    def transcribe_chunk(self, pcm, cancelled: Callable[[], bool]) -> list[Segment]:
        if cancelled():
            return []
        return [Segment(0, 100, "fake")]


def create_app(backend, decode) -> FastAPI:
    app = FastAPI()
    cancelled = threading.Event()
    pipeline = FilePipeline(backend)
    progress_state = {"progress": 0.0, "phase": "idle"}

    def is_cancelled() -> bool:
        return cancelled.is_set()

    def set_progress(value: float, phase: str) -> None:
        progress_state["progress"] = float(value)
        progress_state["phase"] = phase

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "device": getattr(backend, "device", "cpu")}

    @app.get("/progress")
    def progress() -> dict:
        return dict(progress_state)

    @app.post("/transcribe_file")
    def transcribe_file(body: TranscribeFileBody):
        cancelled.clear()
        set_progress(0.0, "starting")

        def tracked_decode(path: str):
            set_progress(0.01, "decode")
            pcm = decode(path)
            set_progress(0.05, "asr")
            return pcm

        def on_progress(value: float) -> None:
            set_progress(0.05 + 0.95 * float(value), "asr")

        try:
            status, segments = pipeline.transcribe(
                body.path,
                cancelled=is_cancelled,
                on_progress=on_progress,
                decode=tracked_decode,
                start_ms=body.start_ms,
                end_ms=body.end_ms,
            )
        except DecodeError as exc:
            logging.exception("decode failed for %s", body.path)
            set_progress(progress_state["progress"], "error")
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception as exc:
            logging.exception("transcribe_file failed for %s", body.path)
            set_progress(progress_state["progress"], "error")
            message = str(exc).strip() or "Ошибка распознавания"
            return JSONResponse(status_code=400, content={"error": message})
        payload = _segments_payload(segments)
        if status == "cancelled":
            set_progress(progress_state["progress"], "cancelled")
            payload["status"] = "cancelled"
            return payload
        set_progress(1.0, "done")
        payload["status"] = "completed"
        return payload

    @app.post("/transcribe_chunk")
    def transcribe_chunk(body: TranscribeChunkBody):
        cancelled.clear()
        try:
            pcm = np.asarray(body.samples, dtype=np.float32)
            segments = backend.transcribe_chunk(pcm, is_cancelled)
        except Exception as exc:
            logging.exception("transcribe_chunk failed")
            message = str(exc).strip() or "Ошибка распознавания"
            return JSONResponse(status_code=400, content={"error": message})
        return _segments_payload(segments)

    @app.post("/cancel")
    def cancel() -> dict:
        cancelled.set()
        return {"ok": True}

    return app


def _decode_pcm(path: str) -> np.ndarray:
    from slysh.decode import decode_pcm_16k_mono

    pcm, _sr = decode_pcm_16k_mono(path)
    return pcm


def _bind_localhost(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(2048)
    return sock


def main(argv: list[str] | None = None) -> None:
    from slysh.logging_setup import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="GigaAM engine HTTP process")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = ephemeral)")
    parser.add_argument("--fake", action="store_true", help="Use a tiny fake ASR backend")
    args = parser.parse_args(argv)

    if args.fake:
        backend = _CliFakeBackend()
    else:
        backend_name = (os.getenv("GIGAAM_ASR_BACKEND") or "gigaam").strip().lower()
        if backend_name == "whisper":
            try:
                from slysh.whisper_backend import load_backend as load_whisper
            except ImportError:
                print(
                    "Whisper backend is not available. Install engine extras.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
            backend = load_whisper(os.getenv("GIGAAM_ASR_PATH"))
        else:
            try:
                from slysh.rnnt_backend import load_backend
            except ImportError:
                print(
                    "GigaAM backend is not available. Start with --fake or install engine extras.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
            backend = load_backend()

    app = create_app(backend=backend, decode=_decode_pcm)
    sock = _bind_localhost(args.port)
    print(f"PORT={sock.getsockname()[1]}", flush=True)
    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
