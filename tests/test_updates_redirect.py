from __future__ import annotations

import pytest

import slysh.updates as updates


def test_validate_download_url_rejects_untrusted_host():
    with pytest.raises(ValueError, match="Недопустимый URL"):
        updates._validate_download_url("https://evil.example/Slysh-Setup.exe")


def test_validate_download_url_accepts_github_asset_cdn():
    updates._validate_download_url(
        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/1.exe"
    )


def test_redirect_handler_rejects_untrusted_location():
    handler = updates._ValidatingRedirectHandler()
    req = updates.urllib.request.Request(
        "https://github.com/o/r/releases/download/v1/Slysh-Setup.exe",
        method="GET",
    )
    with pytest.raises(ValueError, match="Недопустимый URL"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {"Location": "https://evil.example/payload.exe"},
            "https://evil.example/payload.exe",
        )
