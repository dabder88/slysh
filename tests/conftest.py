import pytest


@pytest.fixture(autouse=True)
def _clear_skip_engine(monkeypatch):
  monkeypatch.delenv("GIGAAM_SKIP_ENGINE", raising=False)
