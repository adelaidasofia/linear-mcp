"""list_issue_statuses."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_issue_statuses(workspace: str | None = None, first: int = 100,
                            after: str | None = None,
                            team_id: str | None = None) -> dict[str, Any]:
        """List workflow states (issue statuses) per team.

        `team_id` scopes results to one team. Omit to list every workflow
        state across the workspace.
        """
        params = {"workspace": workspace, "first": first, "after": after, "team_id": team_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return run_tool(
            "list_issue_statuses", params,
            lambda: client_for(workspace).request(queries.LIST_ISSUE_STATUSES, variables),
            lambda r: page_summary(r, "workflowStates"),
        )

    @mcp.tool()
    def get_issue_status(issue_id: str, workspace: str | None = None) -> dict[str, Any]:
        """Return the current workflow state for one issue (id or identifier).

        Convenience tool: the existing get_issue already returns state, but
        this is the minimal-fields variant for status-driven automations.
        """
        params = {"workspace": workspace, "issue_id": issue_id}
        return run_tool(
            "get_issue_status", params,
            lambda: client_for(workspace).request(queries.ISSUE_STATUS_LOOKUP, {"id": issue_id}),
            lambda r: ((r.get("issue") or {}).get("state") or {}).get("name", "missing"),
        )
