"""list_users + get_user."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_users(workspace: str | None = None, first: int = 50,
                   after: str | None = None,
                   include_disabled: bool = False) -> dict[str, Any]:
        """List users in a Linear workspace.

        `include_disabled` flips the Linear `includeDisabled` filter so you
        can see members who have been removed from the org.
        """
        params = {"workspace": workspace, "first": first, "after": after,
                  "include_disabled": include_disabled}
        return run_tool(
            "list_users", params,
            lambda: client_for(workspace).request(
                queries.LIST_USERS,
                {"first": first, "after": after, "includeDisabled": include_disabled},
            ),
            lambda r: page_summary(r, "users"),
        )

    @mcp.tool()
    def get_user(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a Linear user by ID. Pass `me` to look up the PAT owner.

        For `me`, the server resolves it via the viewer query and substitutes
        the resolved id.
        """
        def _run() -> dict:
            client = client_for(workspace)
            target = id
            if id.lower() == "me":
                target = (client.viewer().get("id") or "").strip()
                if not target:
                    raise RuntimeError("could not resolve `me` to a user id")
            return client.request(queries.GET_USER, {"id": target})

        return run_tool(
            "get_user", {"workspace": workspace, "id": id}, _run,
            lambda r: ((r.get("user") or {}).get("name") or "missing"),
        )
