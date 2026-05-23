"""list_issue_labels + create_issue_label."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_issue_labels(workspace: str | None = None, first: int = 100,
                          after: str | None = None,
                          team_id: str | None = None) -> dict[str, Any]:
        """List issue labels. `team_id` scopes to one team; omit for org-wide."""
        params = {"workspace": workspace, "first": first, "after": after, "team_id": team_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return run_tool(
            "list_issue_labels", params,
            lambda: client_for(workspace).request(queries.LIST_ISSUE_LABELS, variables),
            lambda r: page_summary(r, "issueLabels"),
        )

    @mcp.tool()
    def create_issue_label(name: str, workspace: str | None = None,
                           team_id: str | None = None,
                           color: str | None = None,
                           description: str | None = None,
                           parent_id: str | None = None) -> dict[str, Any]:
        """Create a new issue label.

        `team_id` makes a team-scoped label. Omit for workspace-scoped.
        `color` is a 7-char hex (`#RRGGBB`). `parent_id` nests this label
        under another (Linear supports two-level label hierarchies).
        """
        params = {
            "workspace": workspace, "name": name, "team_id": team_id,
            "color": color, "description": description, "parent_id": parent_id,
        }
        input_payload = clean({
            "name": name,
            "teamId": team_id,
            "color": color,
            "description": description,
            "parentId": parent_id,
        })
        return run_tool(
            "create_issue_label", params,
            lambda: client_for(workspace).request(
                queries.LABEL_CREATE, {"input": input_payload}
            ),
            lambda r: ((r.get("issueLabelCreate") or {}).get("issueLabel") or {}).get("name", "?"),
        )
