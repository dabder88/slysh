from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from slysh.api import create_ui_app
from slysh.app import JsApi
from slysh.db import Database
from slysh.paths import db_path


def _fetch(url: str, timeout: float = 5.0) -> tuple[float, int]:
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        size = len(resp.read())
    return time.perf_counter() - started, size


def main() -> int:
    api = JsApi()
    if "window" in vars(api):
        print("FAIL: JsApi exposes public window attribute")
        return 1

    db = Database(db_path())
    recovered = db.recover_stale_state()
    print(f"recovered stale states: {recovered}")

    app = create_ui_app(db, engine=None, auto_start_engine=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            print("FAIL: uvicorn did not start in 10s")
            return 1
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    for path in ("/", "/api/library", "/api/status", "/api/compute", "/api/mics"):
        url = base + path
        try:
            elapsed, size = _fetch(url, timeout=15 if path == "/api/compute" else 5)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"FAIL: {path} -> {exc}")
            return 1
        print(f"OK {path}: {elapsed:.3f}s ({size} bytes)")
        if elapsed > 12:
            print(f"WARN: {path} is slow ({elapsed:.1f}s)")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        check=False,
    )
    if result.returncode != 0:
        print("FAIL: pytest failed")
        return result.returncode
    print("pytest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
