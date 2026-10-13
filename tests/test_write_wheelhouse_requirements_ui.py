from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from write_wheelhouse_requirements_ui import build_requirements_ui


def test_build_requirements_ui_hash_free_and_includes_slysh(tmp_path: Path):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    (wh / "proxy_tools-0.1.0-py3-none-any.whl").write_bytes(b"x")
    (wh / "slysh-1.0.0-py3-none-any.whl").write_bytes(b"x")
    export = tmp_path / "export.txt"
    export.write_text(
        "proxy-tools==0.1.0 \\\n"
        "    --hash=sha256:ccb3751f529c047e2d8a58440d86b205303cf0fe8146f784d1cbcd94f0a28010\n",
        encoding="utf-8",
    )
    out = wh / "requirements-ui.txt"
    build_requirements_ui(export, wh, "1.0.0", out)
    text = out.read_text(encoding="utf-8")
    assert "--hash" not in text
    assert "proxy-tools==0.1.0" in text
    assert "slysh==1.0.0" in text
