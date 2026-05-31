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
import random
import time
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


def is_rate_limited(status_code: int, payload: dict | None) -> bool:
    """True if a Linear response indicates rate limiting.

    Linear surfaces rate limits as **HTTP 400** with
    ``errors[].extensions.code == "RATELIMITED"`` (GraphQL-level), and may also
    use a bare **HTTP 429** for the request-count limiter. A normal validation
    400 (e.g. INVALID_INPUT) is NOT a rate limit and must not be retried.

    Source-of-truth: https://linear.app/developers/rate-limiting
    """
    if status_code == 429:
        return True
    if not payload:
        return False
    for err in payload.get("errors") or []:
        ext = err.get("extensions") or {}
        code = str(ext.get("code") or ext.get("type") or "").upper()
        if code == "RATELIMITED":
            return True
        if "rate limit" in str(err.get("message") or "").lower():
            return True
    return False


# Limiter header pairs: (remaining, reset). Linear resets are UTC epoch-MS.
_RESET_LIMITERS = (
    ("X-RateLimit-Requests-Remaining", "X-RateLimit-Requests-Reset"),
    ("X-RateLimit-Complexity-Remaining", "X-RateLimit-Complexity-Reset"),
)


def seconds_until_reset(headers, now_s: float) -> float | None:
    """Seconds to wait until the rate limit refills, from Linear's reset headers.

    Linear sends **no** ``Retry-After``; it sends ``X-RateLimit-*-Reset`` as a
    UTC epoch-MILLISECOND timestamp. When a specific limiter is exhausted
    (``*-Remaining`` is 0), wait on THAT limiter's reset; otherwise fall back to
    the latest reset present. Returns ``None`` when no reset header is present,
    and never returns a negative wait.
    """
    candidates: list[tuple[bool, int]] = []  # (exhausted, reset_ms)
    for rem_key, reset_key in _RESET_LIMITERS:
        reset_raw = headers.get(reset_key)
        if reset_raw is None:
            continue
        try:
            reset_ms = int(reset_raw)
        except (TypeError, ValueError):
            continue
        rem_raw = headers.get(rem_key)
        try:
            exhausted = rem_raw is not None and int(rem_raw) <= 0
        except (TypeError, ValueError):
            exhausted = False
        candidates.append((exhausted, reset_ms))
    if not candidates:
        return None
    exhausted_resets = [r for ex, r in candidates if ex]
    chosen_ms = max(exhausted_resets) if exhausted_resets else max(r for _, r in candidates)
    return max(0.0, chosen_ms / 1000.0 - now_s)


# Retry tunables (env-overridable). Defaults chosen for the multi-session
# workload: short waits because Linear's leaky bucket refills continuously, a
# hard per-call cap so a single tool call never hangs, jitter so N concurrent
# sessions don't retry in lockstep.
RATE_LIMIT_MAX_RETRIES = int(os.environ.get("LINEAR_RATE_LIMIT_MAX_RETRIES", "5"))
RATE_LIMIT_MAX_WAIT_S = float(os.environ.get("LINEAR_RATE_LIMIT_MAX_WAIT_S", "60"))
RATE_LIMIT_BASE_WAIT_S = float(os.environ.get("LINEAR_RATE_LIMIT_BASE_WAIT_S", "1"))
RATE_LIMIT_JITTER_S = float(os.environ.get("LINEAR_RATE_LIMIT_JITTER_S", "0.5"))


def retry_wait_seconds(
    headers,
    now_s: float,
    attempt: int,
    *,
    cap: float = RATE_LIMIT_MAX_WAIT_S,
    base: float = RATE_LIMIT_BASE_WAIT_S,
    jitter: float = RATE_LIMIT_JITTER_S,
    rand=random.random,
) -> float:
    """How long to sleep before the next retry.

    Reset header is authoritative when present (Linear tells us exactly when the
    bucket refills); otherwise fall back to exponential backoff by ``attempt``.
    Either way the wait is clamped to ``cap`` and a jitter of up to ``jitter``
    seconds is added so concurrent sessions de-synchronise.
    """
    reset = seconds_until_reset(headers, now_s)
    if reset is not None:
        wait = min(reset, cap)
    else:
        wait = min(base * (2 ** attempt), cap)
    return wait + rand() * jitter


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
    `X-RateLimit-{Requests,Complexity}-{Limit,Remaining,Reset}` per
    authenticated user (shared across that user's PATs). Reset values are
    UTC epoch-MILLISECOND timestamps. See https://linear.app/developers/rate-limiting.

    request() retries automatically on rate limiting / 5xx / network blips with
    jittered backoff (see retry_wait_seconds); injectable http_client / sleep /
    clock keep it unit-testable.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        http_client: httpx.Client | None = None,
        sleep=time.sleep,
        clock=time.time,
    ) -> None:
        self.workspace = workspace
        # http_client/sleep/clock are injectable for tests; production uses the
        # pooled per-token client, real time.sleep, and real time.time.
        self.http = http_client if http_client is not None else _http_client(workspace.token)
        self._sleep = sleep
        self._clock = clock
        # Per-client mutable state; OK for stdio (single process, single in-flight call).
        self.last_rate_limit: dict[str, Any] = {}

    def _capture_rate_limit(self, headers) -> None:
        rl: dict[str, Any] = {}
        for src_key, out_key in (
            ("X-RateLimit-Requests-Limit", "requests_limit"),
            ("X-RateLimit-Requests-Remaining", "requests_remaining"),
            ("X-RateLimit-Requests-Reset", "requests_reset"),
            # Canonical names per https://linear.app/developers/rate-limiting
            # (the old X-Complexity-* names captured nothing).
            ("X-RateLimit-Complexity-Limit", "complexity_limit"),
            ("X-RateLimit-Complexity-Remaining", "complexity_remaining"),
            ("X-RateLimit-Complexity-Reset", "complexity_reset"),
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

        Retries automatically on rate limiting (Linear returns **HTTP 400 +
        RATELIMITED** with no Retry-After — we wait on ``X-RateLimit-*-Reset``),
        on 5xx, and on transient network errors, with jittered backoff bounded
        by ``RATE_LIMIT_MAX_RETRIES`` and a per-wait cap. Does NOT retry auth
        failures or ordinary GraphQL errors (those won't fix with a retry).
        Raises LinearError on auth failure, a non-transient GraphQL error, or
        once the retry budget is exhausted. Side effect: updates
        ``self.last_rate_limit`` from response headers on every attempt.
        """
        body = {"query": query}
        if variables is not None:
            body["variables"] = variables
        payload_bytes = json.dumps(body)

        last_error: LinearError | None = None
        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            attempts_left = attempt < RATE_LIMIT_MAX_RETRIES

            # --- send (network errors are transient) ---
            try:
                resp = self.http.post("", content=payload_bytes)
            except httpx.RequestError as e:
                last_error = LinearError(f"network error: {e}")
                if attempts_left:
                    self._sleep(retry_wait_seconds({}, self._clock(), attempt))
                    continue
                raise last_error from e

            # Capture rate-limit headers from every response, including errors.
            self._capture_rate_limit(resp.headers)

            # --- auth: never retry, a new token is required ---
            if resp.status_code == 401:
                raise LinearError(
                    f"unauthorized: PAT for workspace '{self.workspace.alias}' was rejected. "
                    "Re-generate at linear.app/settings/account/security.",
                    status=401,
                )

            # --- parse body (5xx may not be JSON) ---
            try:
                payload = resp.json()
            except ValueError:
                payload = None

            # --- rate limited: wait on the reset header and retry ---
            if is_rate_limited(resp.status_code, payload):
                last_error = LinearError(
                    f"rate limited (HTTP {resp.status_code}) after {attempt + 1} attempt(s); "
                    "queued for retry exhausted",
                    status=resp.status_code,
                )
                if attempts_left:
                    self._sleep(retry_wait_seconds(resp.headers, self._clock(), attempt))
                    continue
                raise last_error

            # --- 5xx: transient, retry with backoff ---
            if resp.status_code >= 500:
                last_error = LinearError(
                    f"linear server error: HTTP {resp.status_code}", status=resp.status_code
                )
                if attempts_left:
                    self._sleep(retry_wait_seconds({}, self._clock(), attempt))
                    continue
                raise last_error

            # --- non-JSON on a non-5xx status: hard failure ---
            if payload is None:
                raise LinearError(
                    f"non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}"
                )

            # --- ordinary GraphQL errors: do NOT retry (won't self-heal) ---
            errors = payload.get("errors") or []
            if errors:
                messages = "; ".join(
                    (e.get("message") or e.get("extensions", {}).get("type") or "unknown")
                    for e in errors
                )
                raise LinearError(f"graphql errors: {messages}", errors=errors, status=resp.status_code)

            return payload.get("data") or {}

        # Defensive: the loop returns on success or raises on the final attempt.
        raise last_error or LinearError("rate limit retry budget exhausted")

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
