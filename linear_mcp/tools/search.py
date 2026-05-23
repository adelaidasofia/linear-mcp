"""Workspace search: search_issues, search_documents, search_projects, semantic_search.

v0.2.0 replaces v0.1.0's `search_documentation` (which hit a non-existent
endpoint — see CHANGELOG) with real GraphQL-backed search across the
workspace's own data.

Confirmed via schema introspection 2026-05-23: Linear's GraphQL exposes
searchIssues, searchDocuments, searchProjects, semanticSearch. There is
NO `searchDocumentation` field. For Linear developer docs, use the docs
site directly at linear.app/developers.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def search_issues(query: str, workspace: str | None = None,
                      first: int = 25, after: str | None = None) -> dict[str, Any]:
        """Full-text search across issues in the workspace.

        Backed by Linear's `searchIssues` GraphQL field (verified via
        introspection). Returns nodes with the standard issue shape plus
        a `totalCount` so the agent knows how many more hits exist beyond
        the current page.
        """
        params = {"workspace": workspace, "query": query, "first": first, "after": after}
        return run_tool(
            "search_issues", params,
            lambda: client_for(workspace).request(
                queries.SEARCH_ISSUES,
                {"term": query, "first": first, "after": after},
            ),
            lambda r: f"{(r.get('searchIssues') or {}).get('totalCount', 0)} total",
        )

    @mcp.tool()
    def search_documents(query: str, workspace: str | None = None,
                         first: int = 25, after: str | None = None) -> dict[str, Any]:
        """Full-text search across workspace documents (NOT Linear's dev docs)."""
        params = {"workspace": workspace, "query": query, "first": first, "after": after}
        return run_tool(
            "search_documents", params,
            lambda: client_for(workspace).request(
                queries.SEARCH_DOCUMENTS,
                {"term": query, "first": first, "after": after},
            ),
            lambda r: f"{(r.get('searchDocuments') or {}).get('totalCount', 0)} total",
        )

    @mcp.tool()
    def search_projects(query: str, workspace: str | None = None,
                        first: int = 25, after: str | None = None) -> dict[str, Any]:
        """Full-text search across projects in the workspace."""
        params = {"workspace": workspace, "query": query, "first": first, "after": after}
        return run_tool(
            "search_projects", params,
            lambda: client_for(workspace).request(
                queries.SEARCH_PROJECTS,
                {"term": query, "first": first, "after": after},
            ),
            lambda r: f"{(r.get('searchProjects') or {}).get('totalCount', 0)} total",
        )

    @mcp.tool()
    def semantic_search(query: str, workspace: str | None = None,
                        first: int = 20, after: str | None = None) -> dict[str, Any]:
        """Semantic search across the entire workspace.

        Returns heterogeneous nodes (issues, projects, documents, comments,
        initiatives). Each node carries `__typename` so the agent can branch
        on entity kind.

        Use this when the search target is conceptual ("payment retry
        logic") rather than exact-string ("PAY-123").
        """
        params = {"workspace": workspace, "query": query, "first": first, "after": after}
        return run_tool(
            "semantic_search", params,
            lambda: client_for(workspace).request(
                queries.SEMANTIC_SEARCH,
                {"term": query, "first": first, "after": after},
            ),
            lambda r: f"{len((r.get('semanticSearch') or {}).get('nodes') or [])} hits",
        )
