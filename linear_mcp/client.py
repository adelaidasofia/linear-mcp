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
from typing import Any

import httpx

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
    """One pooled httpx client per token."""
    return httpx.Client(
        base_url=API_URL,
        timeout=TIMEOUT,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": "linear-mcp/0.1.0 (https://github.com/adelaidasofia/linear-mcp)",
        },
    )


class LinearClient:
    """Per-workspace GraphQL client. Construct from a Workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.http = _http_client(workspace.token)

    def request(self, query: str, variables: dict | None = None) -> dict:
        """POST a GraphQL operation and return the `data` field.

        Raises LinearError on HTTP failure or `errors[]` in the response.
        """
        body = {"query": query}
        if variables is not None:
            body["variables"] = variables
        try:
            resp = self.http.post("", content=json.dumps(body))
        except httpx.RequestError as e:
            raise LinearError(f"network error: {e}") from e
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
