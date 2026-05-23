"""list_teams + get_team."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_teams(workspace: str | None = None, first: int = 50,
                   after: str | None = None) -> dict[str, Any]:
        """List teams in a Linear workspace.

        `workspace` selects which configured PAT to use (defaults to primary).
        `first` is the page size (max 250); `after` is the cursor from a
        previous response's pageInfo.endCursor.
        """
        params = {"workspace": workspace, "first": first, "after": after}
        return run_tool(
            "list_teams", params,
            lambda: client_for(workspace).request(
                queries.LIST_TEAMS, {"first": first, "after": after}
            ),
            lambda r: page_summary(r, "teams"),
        )

    @mcp.tool()
    def get_team(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a Linear team by its UUID. Includes workflow states inline."""
        return run_tool(
            "get_team", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_TEAM, {"id": id}),
            lambda r: ((r.get("team") or {}).get("name") or "missing"),
        )
