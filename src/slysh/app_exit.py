from __future__ import annotations


def should_prompt_before_close(
    skip_exit_confirm: bool,
    user_approved_exit: bool,
) -> bool:
    """Return True if the UI should show the exit confirmation modal."""
    if user_approved_exit or skip_exit_confirm:
        return False
    return True
