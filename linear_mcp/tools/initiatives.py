"""list_initiatives + get_initiative + save_initiative."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_initiatives(workspace: str | None = None, first: int = 50,
                         after: str | None = None) -> dict[str, Any]:
        """List initiatives in the workspace.

        Initiatives are Linear's top-level org-wide goals that contain
        multiple projects.
        """
        params = {"workspace": workspace, "first": first, "after": after}
        return run_tool(
            "list_initiatives", params,
            lambda: client_for(workspace).request(
                queries.LIST_INITIATIVES, {"first": first, "after": after}
            ),
            lambda r: page_summary(r, "initiatives"),
        )

    @mcp.tool()
    def get_initiative(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get an initiative by UUID."""
        return run_tool(
            "get_initiative", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_INITIATIVE, {"id": id}),
            lambda r: ((r.get("initiative") or {}).get("name") or "missing"),
        )

    @mcp.tool()
    def save_initiative(workspace: str | None = None,
                        id: str | None = None,
                        name: str | None = None,
                        description: str | None = None,
                        content: str | None = None,
                        owner_id: str | None = None,
                        status: str | None = None,
                        target_date: str | None = None,
                        color: str | None = None,
                        icon: str | None = None) -> dict[str, Any]:
        """Create or update an initiative.

        Pass `id` to update; omit to create. Status is one of `Planned`,
        `Active`, `Completed` (string, not enum) per Linear's API.
        """
        params = {
            "workspace": workspace, "id": id, "name": name, "description": description,
            "content": content, "owner_id": owner_id, "status": status,
            "target_date": target_date, "color": color, "icon": icon,
        }
        client = client_for(workspace)
        input_payload = clean({
            "name": name,
            "description": description,
            "content": content,
            "ownerId": owner_id,
            "status": status,
            "targetDate": target_date,
            "color": color,
            "icon": icon,
        })
        if id:
            return run_tool(
                "save_initiative (update)", params,
                lambda: client.request(queries.INITIATIVE_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("initiativeUpdate") or {}).get("initiative") or {}).get("name", "?"),
            )
        if not name:
            raise ValueError("save_initiative: `name` required to create a new initiative")
        return run_tool(
            "save_initiative (create)", params,
            lambda: client.request(queries.INITIATIVE_CREATE, {"input": input_payload}),
            lambda r: ((r.get("initiativeCreate") or {}).get("initiative") or {}).get("name", "?"),
        )
