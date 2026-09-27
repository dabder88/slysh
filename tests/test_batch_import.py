from pathlib import Path

from slysh.batch_import import scan_folder, scan_paths


def test_scan_folder_flat(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("nope")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "c.mp3").write_bytes(b"y")
    found = scan_folder(tmp_path, recursive=False)
    assert found == [str((tmp_path / "a.wav").resolve())]


def test_scan_folder_recursive(tmp_path):
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "c.mp3").write_bytes(b"y")
    found = scan_folder(tmp_path, recursive=True)
    assert len(found) == 1
    assert found[0].endswith("c.mp3")


def test_scan_paths_mixed(tmp_path):
    folder = tmp_path / "dir"
    folder.mkdir()
    wav = tmp_path / "one.wav"
    wav.write_bytes(b"x")
    (folder / "two.webm").write_bytes(b"y")
    found = scan_paths([str(wav), str(folder)], recursive=False)
    assert len(found) == 2
