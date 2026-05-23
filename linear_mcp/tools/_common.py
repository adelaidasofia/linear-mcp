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


# --- Auto-pagination helper -------------------------------------------------

MAX_AUTO_PAGES = 20  # cap on safety: never let an agent fan out >20 pages × 250 nodes = 5000 records


def paginate_all(client, query: str, base_variables: dict, node_key: str,
                 page_size: int = 250, max_pages: int = MAX_AUTO_PAGES) -> dict:
    """Walk every page of a list query, return aggregated `nodes`.

    Stops at `max_pages` (default 20) to keep one-shot calls bounded; the
    caller can opt into deeper walks by raising max_pages, but the
    default protects against accidentally pulling tens of thousands of
    records into an MCP response.

    Returns a dict shaped like a single-page response: `{node_key: {nodes: [...], pageInfo: {...}, totalCount: N}}`
    where pageInfo reflects the LAST page walked (so callers can detect
    "we hit max_pages and there were more").
    """
    all_nodes: list = []
    pages_walked = 0
    cursor: str | None = base_variables.get("after")
    last_page: dict = {}
    total_count: int | None = None

    while True:
        variables = {**base_variables, "first": page_size, "after": cursor}
        resp = client.request(query, variables)
        page = resp.get(node_key) or {}
        nodes = page.get("nodes") or []
        all_nodes.extend(nodes)
        last_page = page
        if total_count is None and "totalCount" in page:
            total_count = page.get("totalCount")
        pages_walked += 1
        page_info = page.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        if pages_walked >= max_pages:
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return {
        node_key: {
            "nodes": all_nodes,
            "pageInfo": last_page.get("pageInfo") or {},
            **({"totalCount": total_count} if total_count is not None else {}),
            "_auto_pagination": {
                "pages_walked": pages_walked,
                "max_pages": max_pages,
                "truncated": pages_walked >= max_pages and (last_page.get("pageInfo") or {}).get("hasNextPage", False),
            },
        }
    }
