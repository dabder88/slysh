from pathlib import Path

from slysh.catalog import FASTER_WHISPER_DOWNLOAD_SIZES, GIGAAM_ID, list_local_catalog, list_models


def _gigaam_root(root: Path) -> Path:
    folder = root / "gigaam"
    folder.mkdir(parents=True)
    (folder / "e2e_rnnt.ckpt").write_bytes(b"ckpt")
    return root


def _whisper_root(root: Path, size: str = "medium") -> Path:
    snap = root / f"models--Systran--faster-whisper-{size}" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    (snap / "model.bin").write_bytes(b"weights")
    return snap


def test_local_catalog_lists_downloadable_placeholders(tmp_path):
    items = list_local_catalog([tmp_path])
    assert items[0].id == GIGAAM_ID
    assert items[0].downloadable and not items[0].ready
    whisper_ids = [item.id for item in items if item.id.startswith("whisper:")]
    assert len(whisper_ids) == len(FASTER_WHISPER_DOWNLOAD_SIZES)


def test_catalog_lists_gigaam_and_whisper(tmp_path):
    giga = _gigaam_root(tmp_path / "a")
    _whisper_root(tmp_path / "a", "medium")
    items = list_models([giga])
    ids = [item.id for item in items]
    assert ids[0] == "gigaam"
    assert "whisper:medium" in ids
    medium = next(item for item in items if item.id == "whisper:medium")
    assert medium.backend == "whisper"
    assert medium.ready
    assert medium.path.endswith("abc")


def test_catalog_dedupes_same_id_across_roots(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _whisper_root(first, "small")
    _whisper_root(second, "small")
    items = list_models([first, second])
    whisper = [item for item in items if item.id == "whisper:small"]
    assert len(whisper) == 1
    assert str(first) in whisper[0].path


def test_catalog_skips_incomplete_whisper(tmp_path):
    snap = tmp_path / "models--Systran--faster-whisper-tiny" / "snapshots" / "x"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    items = list_models([tmp_path])
    assert items == []


def test_catalog_flat_faster_whisper_folder(tmp_path):
    folder = tmp_path / "faster-whisper-base"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "pytorch_model.bin").write_bytes(b"w")
    items = list_models([tmp_path])
    assert [item.id for item in items] == ["whisper:base"]


def test_catalog_openai_pt_files(tmp_path):
    folder = tmp_path / "whisper"
    folder.mkdir()
    (folder / "medium.pt").write_bytes(b"pt")
    (folder / "small.pt").write_bytes(b"pt")
    items = list_models([tmp_path])
    ids = [item.id for item in items]
    assert "whisper:medium" in ids
    assert "whisper:small" in ids
    medium = next(item for item in items if item.id == "whisper:medium")
    assert medium.path.endswith("medium.pt")
    assert medium.backend == "whisper"


def test_catalog_prefers_faster_whisper_over_pt(tmp_path):
    snap = tmp_path / "models--Systran--faster-whisper-medium" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    (snap / "model.bin").write_bytes(b"w")
    folder = tmp_path / "whisper"
    folder.mkdir()
    (folder / "medium.pt").write_bytes(b"pt")
    items = list_models([tmp_path])
    medium = next(item for item in items if item.id == "whisper:medium")
    assert medium.path.endswith("abc")
