"""LinearClient — thin GraphQL wrapper.

Per-workspace client. Sends GraphQL POSTs to api.linear.app/graphql with
the workspace's PAT in the Authorization header (no Bearer prefix; that
is Linear's documented format).

Pagination uses the standard Relay-cursor pattern (first / after /
pageInfo). The client exposes a single `request(query, variables)` call;
each tool composes the query it needs.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any  # noqa: F401  (used in LinearClient.last_rate_limit annotation)
from urllib.parse import urlparse

import httpx

from mycelium_security import UnsafeURL, assert_public_ip, sanitize_or_raise

from .workspaces import Workspace

log = logging.getLogger("linear-mcp.client")

API_URL = os.environ.get("LINEAR_API_URL", "https://api.linear.app/graphql")
TIMEOUT = float(os.environ.get("LINEAR_HTTP_TIMEOUT", "30"))


class LinearError(RuntimeError):
    """Wraps a GraphQL error or HTTP failure."""

    def __init__(self, message: str, *, errors: list[dict] | None = None, status: int | None = None):
        super().__init__(message)
        self.errors = errors or []
        self.status = status


@lru_cache(maxsize=8)
def _http_client(token: str) -> httpx.Client:
    """One pooled httpx client per token.

    SSRF hardening (MYC-101): validate API_URL once at client construction
    (since base_url is pinned for the client's lifetime), block 3xx
    redirects so a malicious LINEAR_API_URL override can't redirect to
    169.254.169.254.
    """
    try:
        safe_url = sanitize_or_raise(API_URL)
        host = urlparse(safe_url).hostname or ""
        assert_public_ip(host)
    except UnsafeURL as exc:
        raise LinearError(
            f"refused (SSRF): LINEAR_API_URL fails URL safety check: {exc}"
        ) from exc

    return httpx.Client(
        base_url=safe_url,
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": "linear-mcp/0.3.1 (https://github.com/adelaidasofia/linear-mcp)",
        },
    )


class LinearClient:
    """Per-workspace GraphQL client. Construct from a Workspace.

    After every request, the latest rate-limit headers are surfaced as
    `self.last_rate_limit` so healthcheck (and any caller that cares) can
    report remaining budget without re-querying. Linear sets
    `X-RateLimit-{Requests-Limit, Requests-Remaining, Requests-Reset}`
    (per-token), plus `X-Complexity-Remaining` (per-token GraphQL cost
    budget). Reset values are Unix timestamps.
    """

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.http = _http_client(workspace.token)
        # Per-client mutable state; OK for stdio (single process, single in-flight call).
        self.last_rate_limit: dict[str, Any] = {}

    def _capture_rate_limit(self, headers) -> None:
        rl: dict[str, Any] = {}
        for src_key, out_key in (
            ("X-RateLimit-Requests-Limit", "requests_limit"),
            ("X-RateLimit-Requests-Remaining", "requests_remaining"),
            ("X-RateLimit-Requests-Reset", "requests_reset"),
            ("X-Complexity-Limit", "complexity_limit"),
            ("X-Complexity-Remaining", "complexity_remaining"),
            ("X-Complexity-Reset", "complexity_reset"),
        ):
            v = headers.get(src_key)
            if v is None:
                continue
            try:
                rl[out_key] = int(v)
            except (ValueError, TypeError):
                rl[out_key] = v
        if rl:
            self.last_rate_limit = rl

    def request(self, query: str, variables: dict | None = None) -> dict:
        """POST a GraphQL operation and return the `data` field.

        Raises LinearError on HTTP failure or `errors[]` in the response.
        Side effect: updates `self.last_rate_limit` from response headers.
        """
        body = {"query": query}
        if variables is not None:
            body["variables"] = variables
        try:
            resp = self.http.post("", content=json.dumps(body))
        except httpx.RequestError as e:
            raise LinearError(f"network error: {e}") from e
        # Capture rate-limit headers from every response, including errors.
        self._capture_rate_limit(resp.headers)
        if resp.status_code == 401:
            raise LinearError(
                f"unauthorized: PAT for workspace '{self.workspace.alias}' was rejected. "
                "Re-generate at linear.app/settings/account/security.",
                status=401,
            )
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "")
            raise LinearError(
                f"rate limited (retry-after: {retry_after or 'unspecified'})",
                status=429,
            )
        if resp.status_code >= 500:
            raise LinearError(f"linear server error: HTTP {resp.status_code}", status=resp.status_code)
        try:
            payload = resp.json()
        except ValueError as e:
            raise LinearError(f"non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}") from e
        errors = payload.get("errors") or []
        if errors:
            messages = "; ".join(
                (e.get("message") or e.get("extensions", {}).get("type") or "unknown")
                for e in errors
            )
            raise LinearError(f"graphql errors: {messages}", errors=errors, status=resp.status_code)
        return payload.get("data") or {}

    def viewer(self) -> dict:
        """Return the authenticated user + their organization. Used by healthcheck."""
        data = self.request(
            "query Viewer { viewer { id name email displayName "
            "organization { id name urlKey } } }"
        )
        return data.get("viewer") or {}

    @property
    def alias(self) -> str:
        return self.workspace.alias
