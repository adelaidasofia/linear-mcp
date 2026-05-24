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

import os
import re
import time
from typing import Any, Callable

from ..audit import audit
from ..client import LinearClient, LinearError
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


# --- v0.3 substrate-layer enforcement helpers --------------------------------
# Codified in BUILD_PROMPT_V03.md after the 2026-05-23 session arc that
# created 55 under-specified issues + duplicate creates + an unauthorized
# bulk-cancel attempt. The convention these helpers enforce previously lived
# only in ⚙️ Meta/rules/linear-session-kickoff.md — advisory markdown that
# different MCP clients (or future sessions that forgot the rule files)
# silently ignored. Moving the check into the substrate means every caller
# gets the same hard floor on issue quality.

SOURCE_PREFIX_RE = re.compile(r"^\s*\[source:\s*([^\]]+?)\s*\]")

_SOURCE_HELP = (
    "Per linear-session-kickoff.md cold-read convention. "
    "Examples: [source: 🍄 Mycelium AI/📝 Meeting Notes/2026-05-22 - ...md] | "
    "[source: ⚙️ Meta/Decisions/<file>.md] | [source: linear-kickoff:<slug>]."
)


def extract_source_key(text: str | None) -> str | None:
    """Return the canonical key from a `[source: <key>]` first line, or None."""
    if not text:
        return None
    m = SOURCE_PREFIX_RE.match(text.lstrip())
    if not m:
        return None
    return m.group(1).strip()


def assert_source_first_line(text: str | None, *, tool: str, field: str) -> str | None:
    """Layer 1: reject CREATE calls that lack a `[source: ...]` first line.

    Returns the canonical key when present. Returns None when the bypass
    env var is set (legacy backfills only). Raises LinearError otherwise.
    """
    if os.environ.get("LINEAR_MCP_SKIP_SOURCE_CHECK"):
        return None
    key = extract_source_key(text)
    if not key:
        raise LinearError(
            f"{tool} requires '[source: <canonical-key>]' as the first line of {field}. "
            f"{_SOURCE_HELP} "
            "Bypass via LINEAR_MCP_SKIP_SOURCE_CHECK=1 (legacy backfills only)."
        )
    return key


def assert_no_duplicate_source(
    client: LinearClient,
    canonical_key: str,
    *,
    query: str,
    response_key: str,
    tool: str,
    save_param: str,
) -> None:
    """Layer 2: search for an existing entity carrying the same `[source:]`
    key and refuse to create a duplicate.

    `response_key` is the GraphQL root field (`searchIssues` or
    `searchProjects`). Bypass via `LINEAR_MCP_SKIP_IDEMPOTENCY=1`.
    """
    if os.environ.get("LINEAR_MCP_SKIP_IDEMPOTENCY"):
        return
    # Linear's searchIssues / searchProjects is full-text + relevance ranked,
    # NOT exact match. Brackets and most punctuation in the term get tokenized
    # away, so a search for "[source: 7f2a9c1d-rot-key-20260523]" returns
    # whatever is most relevant by remaining token overlap (e.g. recent issues
    # mentioning "source" / "key" / "rot") — even when no entity actually
    # carries that canonical key. Fix: fetch a window of candidates ranked by
    # relevance, then filter client-side by extracting the `[source:]` first
    # line of each result's description (or content, for projects) and exact-
    # matching against the canonical key. True duplicates surface at high
    # rank; coincidental token matches drop out of the filter.
    term = f"[source: {canonical_key}]"
    resp = client.request(query, {"term": term, "first": 25})
    nodes = (resp.get(response_key) or {}).get("nodes") or []
    match = None
    for node in nodes:
        body = node.get("description") or node.get("content") or ""
        if extract_source_key(body) == canonical_key:
            match = node
            break
    if match is None:
        return
    label = match.get("identifier") or match.get("name") or match.get("id") or "?"
    title = match.get("title") or match.get("name") or ""
    raise LinearError(
        f"{tool}: entity with source key '{canonical_key}' already exists: "
        f"{label} ({title}). "
        f"Use {tool}({save_param}='{match.get('id')}', ...) to update instead. "
        f"Bypass via LINEAR_MCP_SKIP_IDEMPOTENCY=1 to force-create a duplicate."
    )


# Layer 3 — bulk_save_issues auth_phrase. Codified after the 2026-05-23
# auto-mode classifier blocked an unauthorized bulk-cancel; without an
# explicit phrase on the tool surface, a single hallucinated arg could
# mass-modify hundreds of pre-existing issues.

BULK_AUTH_PHRASES = (
    "go",
    "yes do it",
    "confirmed",
    "execute",
    "go cancel",
    "go update",
)


def assert_bulk_auth_phrase(auth_phrase: str | None) -> None:
    """Layer 3: require an explicit auth phrase on bulk mutations."""
    if not auth_phrase or auth_phrase.strip().lower() not in BULK_AUTH_PHRASES:
        raise LinearError(
            f"bulk_save_issues requires auth_phrase param (one of: {BULK_AUTH_PHRASES}). "
            "This protects against accidental mass-modification of pre-existing "
            "shared workspace data. "
            f"Got: {auth_phrase!r}. "
            "Codified 2026-05-23 after the auto-mode classifier denied an "
            "unauthorized bulk-cancel."
        )
