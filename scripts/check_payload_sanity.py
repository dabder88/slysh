"""Wave E.3: payload must not ship secrets, user DB, or builder-only absolute paths."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "dist" / "payload"

FORBIDDEN_NAMES = frozenset(
    {
        "app.db",
        ".env",
        "credentials.json",
        "secrets.dpapi",
    }
)
SECRET_MARKERS = (
    "sk-or-",
    "sk-proj-",
    "OPENAI_API_KEY=",
    "GROQ_API_KEY=",
)
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".pth",
        ".txt",
        ".json",
        ".bat",
        ".ps1",
        ".md",
        ".toml",
        ".lock",
        ".py",
        ".js",
        ".html",
        ".css",
    }
)


def _fail(msg: str) -> int:
    print(f"check_payload_sanity: FAIL: {msg}", file=sys.stderr)
    return 1


def _scan_text(path: Path, issues: list[str]) -> None:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        issues.append(f"read {path}: {exc}")
        return
    for marker in SECRET_MARKERS:
        if marker in data:
            issues.append(f"secret marker {marker!r} in {path.relative_to(PAYLOAD)}")
    user = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if user and len(user) > 3:
        norm_user = user.replace("/", "\\")
        if norm_user.lower() in data.lower() and "payload" not in data.lower():
            # Allow references only if under generic patterns
            if "Slysh-prod" in data or "ProjectsAI" in data:
                issues.append(
                    f"builder path under USERPROFILE in {path.relative_to(PAYLOAD)}"
                )


def main() -> int:
    if not PAYLOAD.is_dir():
        return _fail(f"missing {PAYLOAD} (run build-installer-payload.ps1)")

    issues: list[str] = []
    for path in PAYLOAD.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PAYLOAD)
        if path.name in FORBIDDEN_NAMES:
            issues.append(f"forbidden file {rel}")
        if "node_modules" in rel.parts:
            continue
        top = rel.parts[0].lower() if rel.parts else ""
        if top in ("web", "src"):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size < 5_000_000:
            _scan_text(path, issues)

    venv = PAYLOAD / ".venv"
    if venv.is_dir():
        pyvenv = venv / "pyvenv.cfg"
        if pyvenv.is_file():
            text = pyvenv.read_text(encoding="utf-8", errors="replace")
            if re.search(r"home\s*=\s*.*\\Users\\.*\\AppData\\Roaming\\uv", text, re.I):
                issues.append("pyvenv.cfg points at uv user cache (not portable)")

    models = PAYLOAD / "models"
    if models.is_dir():
        for weight in models.rglob("*"):
            if weight.is_file() and weight.suffix.lower() in {".bin", ".pt", ".onnx", ".ckpt"}:
                if weight.name != ".gitkeep":
                    issues.append(f"model weight in payload: {weight.relative_to(PAYLOAD)}")

    if issues:
        for item in issues[:20]:
            print(item, file=sys.stderr)
        if len(issues) > 20:
            print(f"... and {len(issues) - 20} more", file=sys.stderr)
        return _fail(f"{len(issues)} issue(s)")
    print("check_payload_sanity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
