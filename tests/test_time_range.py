from slysh.time_range import normalize_range
import pytest


def test_normalize_range_empty():
    assert normalize_range(None, None) == (None, None)


def test_normalize_range_rejects_inverted():
    with pytest.raises(ValueError, match="позже начала"):
        normalize_range(5000, 1000)
