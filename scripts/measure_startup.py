from __future__ import annotations

import threading
import time
import urllib.request

import uvicorn

from slysh.api import create_ui_app
from slysh.db import Database
from slysh.paths import db_path


def main() -> None:
    t0 = time.perf_counter()
    app = create_ui_app(Database(db_path()), engine=None)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    t_server = time.perf_counter()
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    for path in ("/api/status", "/api/setup"):
        url = base + path
        while True:
            try:
                with urllib.request.urlopen(url) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.01)
    t_ready = time.perf_counter()
    print(f"uvicorn_started_sec={t_server - t0:.3f}")
    print(f"api_ready_sec={t_ready - t0:.3f}")


if __name__ == "__main__":
    main()
