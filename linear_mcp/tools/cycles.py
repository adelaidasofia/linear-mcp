"""list_cycles."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_cycles(workspace: str | None = None, first: int = 50,
                    after: str | None = None,
                    team_id: str | None = None) -> dict[str, Any]:
        """List cycles, optionally scoped to one team.

        `team_id` is the team UUID. Omit to list cycles across every team.
        """
        params = {"workspace": workspace, "first": first, "after": after, "team_id": team_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return run_tool(
            "list_cycles", params,
            lambda: client_for(workspace).request(queries.LIST_CYCLES, variables),
            lambda r: page_summary(r, "cycles"),
        )
