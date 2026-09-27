from __future__ import annotations

import json
import threading
import time
import urllib.request

import uvicorn

from slysh.api import create_ui_app, model_is_ready
from slysh.db import Database
from slysh.paths import db_path


def main() -> None:
    db = Database(db_path())
    print("db:", db_path())
    jobs = db.list_jobs()
    print("jobs:", len(jobs))
    if jobs:
        statuses: dict[str, int] = {}
        for job in jobs:
            statuses[job["status"]] = statuses.get(job["status"], 0) + 1
        print("statuses:", statuses)
    print("recover:", db.recover_stale_state())

    t0 = time.perf_counter()
    model_is_ready()
    print(f"model_is_ready: {time.perf_counter() - t0:.3f}s")

    t0 = time.perf_counter()
    grouped = db.list_jobs_grouped()
    print(
        f"list_jobs_grouped: {time.perf_counter() - t0:.3f}s "
        f"batches={len(grouped['batches'])} orphans={len(grouped['orphans'])}"
    )

    app = create_ui_app(db, engine=None, auto_start_engine=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    for path in ("/api/status", "/api/compute", "/api/library", "/"):
        t0 = time.perf_counter()
        with urllib.request.urlopen(base + path) as resp:
            body = resp.read()
        print(f"{path}: {time.perf_counter() - t0:.3f}s, {len(body)} bytes")


if __name__ == "__main__":
    main()
