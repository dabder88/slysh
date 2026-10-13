"""Client-side normalizeFavoriteDirPath is mirrored here for API save expectations."""
from __future__ import annotations

import re

_EXPORT_FILE_EXT_RE = re.compile(r"\.(srt|vtt|txt|md|json|ass|ssa)$", re.I)


def normalize_favorite_dir_path(path: object) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    base = value.replace("\\", "/").split("/")[-1]
    if _EXPORT_FILE_EXT_RE.search(base):
        slash = max(value.rfind("/"), value.rfind("\\"))
        if slash > 0:
            value = value[:slash]
    return value.strip()


def test_normalize_favorite_dir_strips_file_name():
    p = r"C:\Users\Anton\AppData\Local\Slysh\recordings\meeting-20261005.srt"
    assert normalize_favorite_dir_path(p) == r"C:\Users\Anton\AppData\Local\Slysh\recordings"


def test_normalize_favorite_dir_keeps_folder():
    p = r"F:\ProjectsAI\Данные\Сторонние проекты\SleePsy\Созвоны"
    assert normalize_favorite_dir_path(p) == p
