"""Live Gladia STT smoke: uses key from Slysh settings or GLADIA_API_KEY (network)."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"smoke_gladia_live: FAIL: {msg}", file=sys.stderr)
    return 1


def _pick_audio() -> Path:
    from slysh.paths import app_dir

    db = app_dir() / "app.db"
    if db.is_file():
        conn = sqlite3.connect(db)
        row = conn.execute(
            """
            SELECT source_path FROM jobs
            WHERE source_path NOT LIKE 'http%'
              AND (source_path LIKE '%.mp3' OR source_path LIKE '%.wav')
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        conn.close()
        if row:
            path = Path(str(row[0]))
            if path.is_file():
                return path
    rec = app_dir() / "recordings"
    if rec.is_dir():
        for ext in ("*.wav", "*.mp3", "*.m4a"):
            hits = sorted(rec.glob(ext), key=lambda p: p.stat().st_mtime, reverse=True)
            if hits:
                return hits[0]
    return Path()


def main() -> int:
    from slysh.providers import get_http_config, save_engine_mode
    from slysh.remote_asr import RemoteAsrError, transcribe_media

    cfg = get_http_config("gladia")
    key_len = len((cfg or {}).get("api_key") or "")
    if key_len == 0:
        key_len = len(os.environ.get("GLADIA_API_KEY", "").strip())
    if key_len == 0:
        return _fail(
            "нет ключа Gladia: сохраните в Настройки → Облако → Gladia "
            "или задайте GLADIA_API_KEY"
        )

    audio = _pick_audio()
    if not audio.is_file():
        return _fail("не найден короткий локальный mp3/wav (jobs или recordings)")

    try:
        save_engine_mode("cloud_only")
    except Exception:
        pass

    print(f"Gladia live: model={(cfg or {}).get('model')} file={audio.name}")
    try:
        segments = transcribe_media(
            backend="http",
            model_id="http:gladia",
            source_path=str(audio),
        )
    except RemoteAsrError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")

    if not segments:
        return _fail("Gladia вернула 0 сегментов")
    preview = (segments[0].text or "").replace("\n", " ")[:100]
    print(f"smoke_gladia_live: OK segments={len(segments)} preview={preview!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
