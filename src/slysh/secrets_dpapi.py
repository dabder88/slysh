"""Windows DPAPI-backed secret blob (wave D)."""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from slysh.paths import app_dir

_LOG = logging.getLogger(__name__)
_STORE_NAME = "secrets.dpapi"


def _store_path() -> Path:
    return app_dir() / _STORE_NAME


def _protect(plain: bytes) -> bytes:
    if sys.platform != "win32":
        return plain
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(plain), ctypes.cast(ctypes.create_string_buffer(plain), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect(cipher: bytes) -> bytes:
    if sys.platform != "win32":
        return cipher
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(cipher), ctypes.cast(ctypes.create_string_buffer(cipher), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def load_secrets() -> dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_bytes()
        if sys.platform == "win32":
            raw = _unprotect(raw)
        else:
            raw = base64.b64decode(raw)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _LOG.warning("secrets store read failed: %s", exc)
        return {}


def save_secrets(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if sys.platform == "win32":
        blob = _protect(payload)
    else:
        blob = base64.b64encode(payload)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def get_nested(path: tuple[str, ...]) -> str:
    node: Any = load_secrets()
    for key in path:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    return str(node or "").strip() if node is not None else ""


def set_nested(path: tuple[str, ...], value: str) -> None:
    data = load_secrets()
    node = data
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[path[-1]] = value
    save_secrets(data)


def clear_nested(path: tuple[str, ...]) -> None:
    data = load_secrets()
    node = data
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            return
        node = child
    node.pop(path[-1], None)
    save_secrets(data)
