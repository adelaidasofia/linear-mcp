"""list_projects + get_project + save_project."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_projects(workspace: str | None = None, first: int = 50,
                      after: str | None = None,
                      team_id: str | None = None,
                      state: str | None = None) -> dict[str, Any]:
        """List projects.

        `team_id` scopes to projects involving one team. `state` filters by
        project state (one of: backlog, planned, started, paused, completed,
        canceled). Omit for all.
        """
        params = {"workspace": workspace, "first": first, "after": after,
                  "team_id": team_id, "state": state}
        f: dict[str, Any] = {}
        if team_id:
            f["accessibleTeams"] = {"some": {"id": {"eq": team_id}}}
        if state:
            f["state"] = {"eq": state}
        variables: dict[str, Any] = {"first": first, "after": after}
        if f:
            variables["filter"] = f
        return run_tool(
            "list_projects", params,
            lambda: client_for(workspace).request(queries.LIST_PROJECTS, variables),
            lambda r: page_summary(r, "projects"),
        )

    @mcp.tool()
    def get_project(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a Linear project by UUID."""
        return run_tool(
            "get_project", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_PROJECT, {"id": id}),
            lambda r: ((r.get("project") or {}).get("name") or "missing"),
        )

    @mcp.tool()
    def save_project(workspace: str | None = None,
                     id: str | None = None,
                     name: str | None = None,
                     description: str | None = None,
                     content: str | None = None,
                     team_ids: list[str] | None = None,
                     lead_id: str | None = None,
                     state: str | None = None,
                     priority: int | None = None,
                     start_date: str | None = None,
                     target_date: str | None = None,
                     color: str | None = None,
                     icon: str | None = None) -> dict[str, Any]:
        """Create or update a Linear project.

        Pass `id` to update an existing project; omit `id` (and pass
        `team_ids`) to create a new one. Linear requires at least one team
        when creating.

        Dates are ISO-8601 strings (`YYYY-MM-DD`). `priority` is 0-4
        (0=none, 1=urgent, 2=high, 3=medium, 4=low).
        """
        params = {
            "workspace": workspace, "id": id, "name": name, "description": description,
            "content": content, "team_ids": team_ids, "lead_id": lead_id, "state": state,
            "priority": priority, "start_date": start_date, "target_date": target_date,
            "color": color, "icon": icon,
        }
        client = client_for(workspace)
        is_update = bool(id)
        input_payload = clean({
            "name": name,
            "description": description,
            "content": content,
            "teamIds": team_ids,
            "leadId": lead_id,
            "state": state,
            "priority": priority,
            "startDate": start_date,
            "targetDate": target_date,
            "color": color,
            "icon": icon,
        })
        if is_update:
            return run_tool(
                "save_project (update)", params,
                lambda: client.request(queries.PROJECT_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("projectUpdate") or {}).get("project") or {}).get("name", "?"),
            )
        if not name or not team_ids:
            raise ValueError("save_project: `name` and `team_ids` required to create a new project")
        return run_tool(
            "save_project (create)", params,
            lambda: client.request(queries.PROJECT_CREATE, {"input": input_payload}),
            lambda r: ((r.get("projectCreate") or {}).get("project") or {}).get("name", "?"),
        )
