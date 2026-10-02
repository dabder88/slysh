from __future__ import annotations

import json

from slysh.release_version import _read_version_json


def test_version_json_utf8_bom(tmp_path):
    path = tmp_path / "version.json"
    payload = {"version": "1.2.3", "github_repo": "o/r"}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    data = _read_version_json(tmp_path)
    assert data.get("version") == "1.2.3"
