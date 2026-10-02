"""Wave A10: Gemini CLI uses temp cwd and @basename, not absolute source path."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slysh.gemini_cli import transcribe_gemini_file  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "clip.mp3"
        audio.write_bytes(b"x")
        seen: dict = {}

        class Proc:
            returncode = 0
            stdout = json.dumps({"text": "ok"})
            stderr = ""

        def runner(cmd, **kwargs):
            seen["cmd"] = cmd
            work = Path(kwargs.get("cwd") or "")
            seen["has_copy"] = (work / "audio.mp3").is_file()
            return Proc()

        segs = transcribe_gemini_file(
            str(audio),
            duration_ms=500,
            runner=runner,
            binary="gemini.exe",
        )
        if not segs or segs[0].text != "ok":
            print("check_gemini_cli_prompt: FAIL segments", file=sys.stderr)
            return 1
        prompt = seen["cmd"][2]
        if "@audio.mp3" not in prompt:
            print(f"check_gemini_cli_prompt: FAIL prompt {prompt!r}", file=sys.stderr)
            return 1
        if not seen.get("has_copy"):
            print("check_gemini_cli_prompt: FAIL missing work copy", file=sys.stderr)
            return 1
    print("check_gemini_cli_prompt: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
