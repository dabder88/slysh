import pytest

from slysh.youtube_ingest import (
    _probe_youtube_reachable_live,
    probe_youtube_reachable,
    reset_youtube_reachability_cache_for_tests,
    youtube_proxy_active,
)


def test_youtube_proxy_active_requires_target_and_host(monkeypatch):
    monkeypatch.setattr(
        "slysh.http_proxy.load_proxy_config",
        lambda: {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8080,
            "targets": {"youtube": True},
        },
    )
    monkeypatch.setattr(
        "slysh.http_proxy.should_use_proxy_for_target",
        lambda tid: tid == "youtube",
    )
    assert youtube_proxy_active() is True

    monkeypatch.setattr(
        "slysh.http_proxy.load_proxy_config",
        lambda: {
            "enabled": True,
            "host": "",
            "port": 8080,
            "targets": {"youtube": True},
        },
    )
    assert youtube_proxy_active() is False


def test_probe_uses_opener_for_target(monkeypatch):
    calls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def getcode(self):
            return 204

    def fake_opener_for_target(target_id: str):
        calls.append(target_id)

        def open_url(request, timeout=8.0):
            url = getattr(request, "full_url", None) or request.get_full_url()
            assert "generate_204" in url
            return FakeResponse()

        return open_url

    monkeypatch.setattr(
        "slysh.http_proxy.opener_for_target",
        fake_opener_for_target,
    )
    reset_youtube_reachability_cache_for_tests()
    assert _probe_youtube_reachable_live(timeout=1.0) is True
    assert calls == ["youtube"]


def test_probe_cache_reuses_result(monkeypatch):
    reset_youtube_reachability_cache_for_tests()
    count = {"n": 0}

    def fake_live(**kwargs):
        count["n"] += 1
        return count["n"] == 1

    monkeypatch.setattr(
        "slysh.youtube_ingest._probe_youtube_reachable_live",
        fake_live,
    )
    assert probe_youtube_reachable(use_cache=True) is True
    assert probe_youtube_reachable(use_cache=True) is True
    assert count["n"] == 1

    reset_youtube_reachability_cache_for_tests()
