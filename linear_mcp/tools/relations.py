"""Issue relations: blocks / blocked-by / duplicates / related.

Linear's IssueRelation entity models the lateral graph between issues.
v0.2 exposes the read + create + delete surface. The four relation
types (`blocks`, `duplicate`, `related`, plus their inverses) are
canonical Linear strings — pass them verbatim as the `type` arg.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary

VALID_TYPES = ("blocks", "duplicate", "related")


def _issue_relation_summary(result: dict[str, Any]) -> str:
    return page_summary(result, "issueRelations")


def _merge_issue_relation_pages(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize Issue.relations + inverseRelations to issueRelations.

    Linear removed `IssueRelationFilter` from the top-level
    `issueRelations` connection. Issue-scoped reads now have to come from
    `issue(id) { relations inverseRelations }`. Returning the historical
    `{"issueRelations": ...}` shape keeps the MCP tool contract stable for
    callers while adding a small `direction` hint per node.
    """
    issue = result.get("issue") or {}
    issue_id = issue.get("id")
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for page_name, direction in (
        ("relations", "outgoing"),
        ("inverseRelations", "incoming"),
    ):
        for node in ((issue.get(page_name) or {}).get("nodes") or []):
            enriched = dict(node)
            enriched["direction"] = direction
            nodes_by_id[enriched["id"]] = enriched

    direct_page = (issue.get("relations") or {}).get("pageInfo") or {}
    inverse_page = (issue.get("inverseRelations") or {}).get("pageInfo") or {}
    return {
        "issue": {
            "id": issue_id,
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
        },
        "issueRelations": {
            "nodes": list(nodes_by_id.values()),
            "pageInfo": {
                "hasNextPage": bool(
                    direct_page.get("hasNextPage")
                    or inverse_page.get("hasNextPage")
                ),
                "endCursor": (
                    direct_page.get("endCursor")
                    or inverse_page.get("endCursor")
                ),
            },
        },
    }


def register(mcp) -> None:
    @mcp.tool()
    def list_issue_relations(workspace: str | None = None, first: int = 50,
                             after: str | None = None,
                             issue_id: str | None = None) -> dict[str, Any]:
        """List issue relations. `issue_id` filters to relations involving one issue."""
        params = {"workspace": workspace, "first": first, "after": after,
                  "issue_id": issue_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if issue_id:
            variables["id"] = issue_id
            fetch = lambda: _merge_issue_relation_pages(
                client_for(workspace).request(
                    queries.GET_ISSUE_RELATIONS, variables
                )
            )
        else:
            fetch = lambda: client_for(workspace).request(
                queries.LIST_ISSUE_RELATIONS, variables
            )
        return run_tool(
            "list_issue_relations", params,
            fetch,
            _issue_relation_summary,
        )

    @mcp.tool()
    def create_issue_relation(issue_id: str, related_issue_id: str,
                              type: str = "related",
                              workspace: str | None = None) -> dict[str, Any]:
        """Create a relation between two issues.

        `type` must be one of: `blocks` (issue blocks related_issue),
        `duplicate` (issue duplicates related_issue), or `related` (no
        directionality). Linear automatically creates the inverse
        relation visible on the other issue.
        """
        if type not in VALID_TYPES:
            raise ValueError(f"type must be one of {VALID_TYPES}, got {type!r}")
        params = {"workspace": workspace, "issue_id": issue_id,
                  "related_issue_id": related_issue_id, "type": type}
        return run_tool(
            "create_issue_relation", params,
            lambda: client_for(workspace).request(
                queries.ISSUE_RELATION_CREATE,
                {"input": {"issueId": issue_id, "relatedIssueId": related_issue_id, "type": type}},
            ),
            lambda r: ((r.get("issueRelationCreate") or {}).get("issueRelation") or {}).get("id", "?"),
        )

    @mcp.tool()
    def delete_issue_relation(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Delete an issue relation by ID. Non-destructive (no cascade)."""
        params = {"workspace": workspace, "id": id}
        return run_tool(
            "delete_issue_relation", params,
            lambda: client_for(workspace).request(queries.ISSUE_RELATION_DELETE, {"id": id}),
            lambda r: "ok" if (r.get("issueRelationDelete") or {}).get("success") else "failed",
        )
