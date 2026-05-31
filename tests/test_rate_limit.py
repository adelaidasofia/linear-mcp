"""Rate-limit resilience tests for LinearClient (Layer 1: detection + retry).

Linear returns rate-limit errors as HTTP 400 with ``errors[].extensions.code
== "RATELIMITED"`` — NOT a clean HTTP 429 — and sends no ``Retry-After``
header, only ``X-RateLimit-*-Reset`` epoch-millisecond timestamps. The old
client only checked ``status_code == 429``, so rate limits fell through to the
generic "graphql errors" raise with zero retry and the write was lost.

These tests pin the corrected contract.
Source-of-truth: https://linear.app/developers/rate-limiting
"""

from __future__ import annotations

import httpx
import pytest


# --- Layer 1a: detection ----------------------------------------------------


def test_detects_ratelimited_graphql_error_on_400():
    """Linear's real shape: HTTP 400 + RATELIMITED code in the errors body."""
    from linear_mcp.client import is_rate_limited

    payload = {
        "errors": [
            {"message": "rate limited", "extensions": {"code": "RATELIMITED"}}
        ]
    }
    assert is_rate_limited(400, payload) is True


def test_detects_plain_http_429():
    """The HTTP-level request-count limiter can still surface as a bare 429."""
    from linear_mcp.client import is_rate_limited

    assert is_rate_limited(429, None) is True


def test_non_ratelimit_400_is_not_detected():
    """A normal validation 400 must NOT be treated as a rate limit (no retry)."""
    from linear_mcp.client import is_rate_limited

    payload = {
        "errors": [
            {"message": "Variable not provided", "extensions": {"code": "INVALID_INPUT"}}
        ]
    }
    assert is_rate_limited(400, payload) is False


def test_success_is_not_ratelimited():
    from linear_mcp.client import is_rate_limited

    assert is_rate_limited(200, {"data": {"viewer": {}}}) is False


# --- Layer 1b: wait derived from reset headers (no Retry-After) --------------


def test_seconds_until_reset_uses_requests_reset_header():
    """Linear sends X-RateLimit-Requests-Reset as a UTC epoch-MILLISECOND value."""
    from linear_mcp.client import seconds_until_reset

    now_s = 1_000_000.0
    headers = {"X-RateLimit-Requests-Reset": str(int((now_s + 30) * 1000))}
    assert seconds_until_reset(headers, now_s) == pytest.approx(30.0, abs=0.01)


def test_seconds_until_reset_uses_complexity_reset_when_that_limiter_is_exhausted():
    """When the COMPLEXITY limiter trips (remaining 0), wait on its reset, not requests'."""
    from linear_mcp.client import seconds_until_reset

    now_s = 1_000_000.0
    headers = {
        "X-RateLimit-Requests-Remaining": "1500",
        "X-RateLimit-Requests-Reset": str(int((now_s + 5) * 1000)),
        "X-RateLimit-Complexity-Remaining": "0",
        "X-RateLimit-Complexity-Reset": str(int((now_s + 42) * 1000)),
    }
    assert seconds_until_reset(headers, now_s) == pytest.approx(42.0, abs=0.01)


def test_seconds_until_reset_none_when_no_reset_header():
    from linear_mcp.client import seconds_until_reset

    assert seconds_until_reset({}, 1_000_000.0) is None


def test_seconds_until_reset_floors_at_zero_for_past_reset():
    """A reset already in the past => 0.0 (never negative)."""
    from linear_mcp.client import seconds_until_reset

    now_s = 1_000_000.0
    headers = {"X-RateLimit-Requests-Reset": str(int((now_s - 5) * 1000))}
    assert seconds_until_reset(headers, now_s) == 0.0


# --- Layer 1c: retry wait policy (reset-first, exp-backoff fallback, capped) -


def _no_jitter():
    return 0.0


def test_retry_wait_prefers_reset_header():
    from linear_mcp.client import retry_wait_seconds

    now_s = 1_000_000.0
    headers = {"X-RateLimit-Requests-Reset": str(int((now_s + 30) * 1000))}
    wait = retry_wait_seconds(headers, now_s, attempt=0, cap=60.0, rand=_no_jitter)
    assert wait == pytest.approx(30.0, abs=0.01)


def test_retry_wait_caps_long_reset():
    """A reset further out than the cap is clamped — a tool call must not hang for an hour."""
    from linear_mcp.client import retry_wait_seconds

    now_s = 1_000_000.0
    headers = {"X-RateLimit-Requests-Reset": str(int((now_s + 3600) * 1000))}
    wait = retry_wait_seconds(headers, now_s, attempt=0, cap=60.0, rand=_no_jitter)
    assert wait == 60.0


def test_retry_wait_exponential_backoff_when_no_reset_header():
    from linear_mcp.client import retry_wait_seconds

    # base 1.0, attempt 3 => 8.0 (no reset header present)
    wait = retry_wait_seconds({}, 1_000_000.0, attempt=3, base=1.0, cap=60.0, rand=_no_jitter)
    assert wait == pytest.approx(8.0, abs=0.01)


def test_retry_wait_backoff_is_capped():
    from linear_mcp.client import retry_wait_seconds

    wait = retry_wait_seconds({}, 1_000_000.0, attempt=10, base=1.0, cap=60.0, rand=_no_jitter)
    assert wait == 60.0


def test_retry_wait_adds_jitter():
    """Jitter is added on top so N concurrent sessions don't retry in lockstep."""
    from linear_mcp.client import retry_wait_seconds

    now_s = 1_000_000.0
    headers = {"X-RateLimit-Requests-Reset": str(int((now_s + 30) * 1000))}
    wait = retry_wait_seconds(
        headers, now_s, attempt=0, cap=60.0, jitter=0.5, rand=lambda: 1.0
    )
    assert wait == pytest.approx(30.5, abs=0.01)


# --- Layer 1d: the retry loop wired into LinearClient.request() --------------

NOW_S = 1_000_000.0
RATELIMITED_BODY = {
    "errors": [{"message": "rate limited", "extensions": {"code": "RATELIMITED"}}]
}


def _reset_headers(seconds_ahead: float) -> dict:
    return {"X-RateLimit-Requests-Remaining": "0",
            "X-RateLimit-Requests-Reset": str(int((NOW_S + seconds_ahead) * 1000))}


def _client_replaying(events):
    """LinearClient whose HTTP layer replays `events` in order.

    Each event is either a callable(request)->httpx.Response, or a tuple
    (status_code, json_body, headers_dict). Sleep is recorded (no real wait);
    clock is fixed at NOW_S. Returns (client, slept_list).
    """
    from linear_mcp.client import LinearClient
    from linear_mcp.workspaces import Workspace

    seq = iter(events)

    def handler(request: httpx.Request) -> httpx.Response:
        event = next(seq)
        if callable(event):
            return event(request)
        status, body, headers = event
        return httpx.Response(status, json=body, headers=headers)

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.linear.app/graphql",
    )
    slept: list[float] = []
    client = LinearClient(
        Workspace(alias="t", token="lin_api_t"),
        http_client=http,
        sleep=lambda s: slept.append(s),
        clock=lambda: NOW_S,
    )
    return client, slept


def test_request_succeeds_first_try_without_sleeping():
    client, slept = _client_replaying([(200, {"data": {"ok": 1}}, {})])
    data = client.request("query { viewer { id } }")
    assert data == {"ok": 1}
    assert slept == []


def test_request_retries_rate_limit_then_succeeds():
    client, slept = _client_replaying([
        (400, RATELIMITED_BODY, _reset_headers(2)),
        (200, {"data": {"ok": 1}}, {}),
    ])
    data = client.request("mutation { issueUpdate { success } }")
    assert data == {"ok": 1}
    assert len(slept) == 1
    assert 2.0 <= slept[0] <= 2.5  # reset wait (2s) + jitter (<=0.5)


def test_request_raises_after_exhausting_rate_limit_retries():
    from linear_mcp.client import LinearError, RATE_LIMIT_MAX_RETRIES

    client, slept = _client_replaying(
        [(400, RATELIMITED_BODY, _reset_headers(1))] * (RATE_LIMIT_MAX_RETRIES + 1)
    )
    with pytest.raises(LinearError) as exc:
        client.request("mutation { issueUpdate { success } }")
    assert "rate limit" in str(exc.value).lower()
    assert len(slept) == RATE_LIMIT_MAX_RETRIES  # sleeps before each retry, not after the last


def test_request_retries_on_5xx_then_succeeds():
    client, slept = _client_replaying([
        (503, {"error": "upstream"}, {}),
        (200, {"data": {"ok": 1}}, {}),
    ])
    data = client.request("query { viewer { id } }")
    assert data == {"ok": 1}
    assert len(slept) == 1


def test_request_retries_on_network_error_then_succeeds():
    def boom(_request):
        raise httpx.ConnectError("connection reset")

    client, slept = _client_replaying([
        boom,
        (200, {"data": {"ok": 1}}, {}),
    ])
    data = client.request("query { viewer { id } }")
    assert data == {"ok": 1}
    assert len(slept) == 1


def test_request_does_not_retry_a_normal_graphql_error():
    """A real validation error must raise immediately — retrying a bug just burns budget."""
    from linear_mcp.client import LinearError

    body = {"errors": [{"message": "Field 'foo' not found",
                        "extensions": {"code": "INVALID_INPUT"}}]}
    client, slept = _client_replaying([(200, body, {})])
    with pytest.raises(LinearError) as exc:
        client.request("query { bad }")
    assert "INVALID_INPUT" in str(exc.value) or "not found" in str(exc.value)
    assert slept == []  # zero retries on a non-transient error


def test_request_does_not_retry_401_unauthorized():
    """Auth failures won't fix with retry — fail fast."""
    from linear_mcp.client import LinearError

    client, slept = _client_replaying([(401, {"error": "unauthorized"}, {})])
    with pytest.raises(LinearError) as exc:
        client.request("query { viewer { id } }")
    assert exc.value.status == 401
    assert slept == []


def test_capture_reads_complexity_from_canonical_header_names():
    """Linear's complexity headers are X-RateLimit-Complexity-* (not X-Complexity-*).

    The old names silently captured nothing, so the complexity budget was
    invisible to healthcheck and to the shared pre-throttle.
    """
    client, _ = _client_replaying([(200, {"data": {}}, {
        "X-RateLimit-Requests-Limit": "2500",
        "X-RateLimit-Requests-Remaining": "2499",
        "X-RateLimit-Complexity-Limit": "3000000",
        "X-RateLimit-Complexity-Remaining": "2999000",
    })])
    client.request("query { viewer { id } }")
    assert client.last_rate_limit["requests_remaining"] == 2499
    assert client.last_rate_limit["complexity_limit"] == 3000000
    assert client.last_rate_limit["complexity_remaining"] == 2999000
