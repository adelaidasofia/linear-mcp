"""search_documentation — search the public Linear developer docs.

This mirrors the official Linear MCP's `search_documentation` tool.
Linear publishes their dev docs at linear.app/developers; we hit the
public Algolia search index that powers the docs site so an agent
working in a Linear context can answer "how do I X?" without leaving
the MCP.

If Linear's docs search ever moves to a different backend, only this
module needs to change.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

import httpx

from ._common import run_tool

DOCS_SEARCH_URL = os.environ.get(
    "LINEAR_DOCS_SEARCH_URL",
    "https://linear.app/api/docs/search",
)


def register(mcp) -> None:
    @mcp.tool()
    def search_documentation(query: str, limit: int = 5) -> dict[str, Any]:
        """Search the Linear developer documentation.

        Returns up to `limit` hits with title, url, and a snippet.
        Useful when an agent needs to look up GraphQL field shapes,
        webhook payloads, or authentication patterns mid-task.
        """
        params = {"query": query, "limit": limit}

        def _run() -> dict[str, Any]:
            try:
                resp = httpx.get(
                    DOCS_SEARCH_URL,
                    params={"q": query, "limit": limit},
                    timeout=15,
                    headers={"User-Agent": "linear-mcp/0.1.0"},
                )
                if resp.status_code != 200:
                    return {
                        "query": query,
                        "hits": [],
                        "warning": (
                            f"docs search returned HTTP {resp.status_code}. "
                            "Try linear.app/developers in a browser."
                        ),
                    }
                data = resp.json() if resp.text.strip().startswith("{") else {}
            except (httpx.RequestError, json.JSONDecodeError) as e:
                return {
                    "query": query,
                    "hits": [],
                    "warning": f"docs search unavailable: {e}",
                    "fallback_url": f"https://linear.app/developers?q={quote(query)}",
                }
            hits = data.get("hits") or data.get("results") or []
            normalized = []
            for hit in hits[:limit]:
                normalized.append({
                    "title": hit.get("title") or hit.get("name") or "",
                    "url": hit.get("url") or hit.get("link") or "",
                    "snippet": (hit.get("snippet") or hit.get("description") or "")[:300],
                })
            return {"query": query, "hits": normalized}

        return run_tool(
            "search_documentation", params, _run,
            lambda r: f"{len(r.get('hits', []))} hits",
        )
