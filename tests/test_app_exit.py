from slysh.app_exit import should_prompt_before_close


def test_should_prompt_before_close_when_neither_skip_nor_approved():
    assert should_prompt_before_close(False, False) is True


def test_should_prompt_before_close_skip_exit_confirm():
    assert should_prompt_before_close(True, False) is False


def test_should_prompt_before_close_user_approved():
    assert should_prompt_before_close(False, True) is False


def test_should_prompt_before_close_both():
    assert should_prompt_before_close(True, True) is False
