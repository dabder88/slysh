import os

from slysh.open_paths import reveal_in_folder, windows_explorer_reveal_args


def test_windows_explorer_reveal_keeps_path_as_own_argument(tmp_path):
    target = tmp_path / "Созвон 18.08.26.srt"
    args = windows_explorer_reveal_args(target)
    assert args[0] == "explorer"
    assert args[1] == "/select,"
    assert args[2] == os.path.normpath(str(target))
    assert " " in args[2]


def test_reveal_in_folder_on_windows_does_not_glue_select_to_path(tmp_path, monkeypatch):
    from slysh import open_paths as module

    folder = tmp_path / "Сторонние проекты"
    folder.mkdir()
    target = folder / "запись.srt"
    target.write_text("ok", encoding="utf-8")
    seen: dict = {}

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda args, **_kwargs: seen.update(args=list(args)),
    )

    reveal_in_folder(str(target))
    assert seen["args"][0] == "explorer"
    assert seen["args"][1] == "/select,"
    assert seen["args"][2] == os.path.normpath(str(target))
