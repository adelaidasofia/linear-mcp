"""SSRF mitigation tests for linear-mcp _http_client (MYC-101).

API_URL is constructed at module-load from LINEAR_API_URL env. To exercise
the validator with different URLs, we reload the client module under
monkeypatched env and observe the LinearError.
"""
from __future__ import annotations

import importlib
import os
import socket
import sys
from unittest.mock import patch

import pytest


def _reload_with_env(url: str):
    """Reimport linear_mcp.client with LINEAR_API_URL=url. Returns module."""
    os.environ["LINEAR_API_URL"] = url
    if "linear_mcp.client" in sys.modules:
        del sys.modules["linear_mcp.client"]
    return importlib.import_module("linear_mcp.client")


class TestSSRFHTTPClient:
    @pytest.fixture(autouse=True)
    def _reset(self):
        # Save original env so subsequent reloads don't clobber.
        original = os.environ.get("LINEAR_API_URL")
        yield
        if original is None:
            os.environ.pop("LINEAR_API_URL", None)
        else:
            os.environ["LINEAR_API_URL"] = original

    def test_rejects_url_with_backslash(self):
        mod = _reload_with_env("https://api.linear.app/\\evil")
        with pytest.raises(mod.LinearError, match="SSRF"):
            mod._http_client("dummy-token-bs")

    def test_rejects_embedded_credentials(self):
        mod = _reload_with_env("https://u:p@api.linear.app/graphql")
        with pytest.raises(mod.LinearError, match="SSRF"):
            mod._http_client("dummy-token-creds")

    def test_rejects_ipv6_link_local(self):
        mod = _reload_with_env("http://[fe80::1]/graphql")
        with pytest.raises(mod.LinearError, match="SSRF"):
            mod._http_client("dummy-token-v6")

    def test_rejects_dns_resolving_to_private_ip(self):
        with patch("mycelium_security.url.socket.getaddrinfo") as mock_resolver:
            mock_resolver.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))
            ]
            mod = _reload_with_env("http://attacker.example.com/graphql")
            with pytest.raises(mod.LinearError, match="SSRF"):
                mod._http_client("dummy-token-dns")

    def test_rejects_aws_metadata_endpoint(self):
        mod = _reload_with_env(
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
        )
        with pytest.raises(mod.LinearError, match="SSRF"):
            mod._http_client("dummy-token-imds")

    def test_follow_redirects_false_on_built_client(self):
        # Use the real Linear URL (public, resolves) to verify the client
        # is constructed with follow_redirects=False.
        mod = _reload_with_env("https://api.linear.app/graphql")
        client = mod._http_client("dummy-token-redirect")
        try:
            assert client.follow_redirects is False
        finally:
            client.close()
