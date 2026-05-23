"""Helpers shared across tool modules.

Keeps tool bodies small: every tool follows the same shape:

    start = time.time()
    try:
        client = client_for(workspace)
        result = client.request(QUERY, variables)
        summary = summarize(result)
        audit(...)
        return result
    except Exception as e:
        audit(... error=str(e))
        raise

The helpers `with_client` and `clean` collapse that into a one-liner.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..audit import audit
from ..client import LinearClient
from ..workspaces import REGISTRY


def client_for(workspace: str | None) -> LinearClient:
    """Resolve a workspace alias to a LinearClient. None → primary."""
    return LinearClient(REGISTRY.get(workspace))


def clean(d: dict | None) -> dict:
    """Remove keys with None values. Linear's optional inputs reject explicit nulls."""
    if not d:
        return {}
    return {k: v for k, v in d.items() if v is not None}


def run_tool(name: str, params: dict, fn: Callable[[], Any], summarize: Callable[[Any], str]) -> Any:
    """Time a tool call, audit it, and return the result (or re-raise)."""
    start = time.time()
    try:
        result = fn()
        summary = summarize(result) if summarize else ""
        audit(name, params, summary, int((time.time() - start) * 1000))
        return result
    except Exception as e:  # noqa: BLE001
        audit(name, params, "", int((time.time() - start) * 1000), str(e))
        raise


def page_summary(result: dict, node_key: str) -> str:
    """Standard list-tool summary: '<n> nodes, <hasNextPage>'."""
    nodes = (result.get(node_key) or {}).get("nodes") or []
    page = (result.get(node_key) or {}).get("pageInfo") or {}
    more = " (more)" if page.get("hasNextPage") else ""
    return f"{len(nodes)} nodes{more}"
