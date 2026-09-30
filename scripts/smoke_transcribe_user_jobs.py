"""Smoke-transcribe idle/failed local file jobs from %LOCALAPPDATA%\\Slysh\\app.db."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
HOME = Path(os.environ.get("LOCALAPPDATA", "")) / "Slysh"
DB = HOME / "app.db"
MAX_FILES = 3
CHUNK_TIMEOUT_S = 600.0
ENGINE_BOOT_WAIT_S = float(os.environ.get("SLYSH_SMOKE_ENGINE_BOOT", "120"))


def _jobs() -> list[tuple[int, str, str]]:
    if not DB.is_file():
        return []
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        """
        SELECT id, status, source_path FROM jobs
        WHERE source_path NOT LIKE 'http%'
          AND source_path LIKE '%.mp3'
          AND status IN ('idle', 'failed')
        ORDER BY id DESC
        LIMIT ?
        """,
        (MAX_FILES,),
    ).fetchall()
    conn.close()
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


def _wait_port(proc: subprocess.Popen, deadline: float) -> int:
    assert proc.stdout is not None
    boot: list[str] = []
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        boot.append(line)
        if line.startswith("PORT="):
            return int(line.strip().split("=", 1)[1])
    tail = "".join(boot[-30:])
    code = proc.poll()
    raise RuntimeError(f"engine did not report PORT (exit={code}):\n{tail}")


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not PYTHON.is_file():
        print("missing venv python", file=sys.stderr)
        return 2
    jobs = _jobs()
    if not jobs:
        print("no idle/failed mp3 jobs in", DB)
        return 0
    env = os.environ.copy()
    env.setdefault("GIGAAM_DESKTOP_HOME", str(HOME))
    env.setdefault("GIGAAM_MODEL_ROOT", str(ROOT / "models"))
    env.setdefault("GIGAAM_PROJECT_MODELS", str(ROOT / "models"))
    env.setdefault("SLYSH_INSTALL_ROOT", str(ROOT))
    cmd = [str(PYTHON), "-m", "slysh.engine_server"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        port = _wait_port(proc, time.monotonic() + ENGINE_BOOT_WAIT_S)
        base = f"http://127.0.0.1:{port}"
        health = json.loads(
            urllib.request.urlopen(f"{base}/health", timeout=10).read().decode("utf-8")
        )
        print("engine device:", health.get("device"))
        ok = 0
        for job_id, status, path in jobs:
            p = Path(path)
            if not p.is_file():
                print(f"job {job_id} skip missing: {path}")
                continue
            print(f"job {job_id} ({status}) transcribe {p.name} ...")
            try:
                out = _post_json(
                    f"{base}/transcribe_file",
                    {"path": str(p)},
                    timeout=CHUNK_TIMEOUT_S,
                )
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                print(f"  FAIL HTTP {exc.code}: {body[:300]}")
                continue
            if out.get("error"):
                print(f"  FAIL: {out['error'][:300]}")
                continue
            segs = out.get("segments") or []
            preview = (segs[0].get("text") if segs else "")[:80]
            print(f"  OK segments={len(segs)} preview={preview!r}")
            ok += 1
        print(f"done {ok}/{len(jobs)}")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
