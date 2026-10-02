from pathlib import Path

import pytest

from slysh.source_path import (
    FILE_NOT_FOUND_MESSAGE,
    NEED_FULL_PATH_MESSAGE,
    normalize_source_path,
    require_existing_file,
)


def test_normalize_strips_quotes_and_file_uri(tmp_path):
    wav = tmp_path / "talk.wav"
    wav.write_bytes(b"RIFF")
    quoted = f'"{wav}"'
    as_uri = wav.resolve().as_uri()
    assert normalize_source_path(quoted) == wav
    assert normalize_source_path(as_uri) == wav.resolve()


def test_require_existing_file_returns_resolved_path(tmp_path):
    wav = tmp_path / "Созвон.webm"
    wav.write_bytes(b"webm")
    assert require_existing_file(str(wav)) == wav.resolve()
    assert require_existing_file(wav.resolve().as_uri()) == wav.resolve()


def test_basename_only_asks_to_use_open_dialog():
    with pytest.raises(ValueError, match="Открыть") as exc:
        require_existing_file("Созвон 11.08.26 - правки.webm")
    assert "Созвон 11.08.26 - правки.webm" in str(exc.value)
    assert str(exc.value) == NEED_FULL_PATH_MESSAGE.format(
        name="Созвон 11.08.26 - правки.webm"
    )


def test_missing_absolute_path_mentions_the_path(tmp_path):
    missing = tmp_path / "gone.wav"
    with pytest.raises(ValueError, match="не найден") as exc:
        require_existing_file(str(missing))
    assert str(missing) in str(exc.value)
    assert str(exc.value) == FILE_NOT_FOUND_MESSAGE.format(path=Path(str(missing)))
