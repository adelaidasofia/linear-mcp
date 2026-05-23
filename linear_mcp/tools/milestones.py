"""list_milestones + get_milestone + save_milestone."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_milestones(workspace: str | None = None, first: int = 50,
                        after: str | None = None,
                        project_id: str | None = None) -> dict[str, Any]:
        """List project milestones. `project_id` scopes to one project."""
        params = {"workspace": workspace, "first": first, "after": after,
                  "project_id": project_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if project_id:
            variables["filter"] = {"project": {"id": {"eq": project_id}}}
        return run_tool(
            "list_milestones", params,
            lambda: client_for(workspace).request(queries.LIST_MILESTONES, variables),
            lambda r: page_summary(r, "projectMilestones"),
        )

    @mcp.tool()
    def get_milestone(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a project milestone by UUID."""
        return run_tool(
            "get_milestone", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_MILESTONE, {"id": id}),
            lambda r: ((r.get("projectMilestone") or {}).get("name") or "missing"),
        )

    @mcp.tool()
    def save_milestone(workspace: str | None = None,
                       id: str | None = None,
                       name: str | None = None,
                       project_id: str | None = None,
                       description: str | None = None,
                       target_date: str | None = None,
                       sort_order: float | None = None) -> dict[str, Any]:
        """Create or update a project milestone.

        Pass `id` to update. Creating requires `name` and `project_id`.
        """
        params = {
            "workspace": workspace, "id": id, "name": name, "project_id": project_id,
            "description": description, "target_date": target_date,
            "sort_order": sort_order,
        }
        client = client_for(workspace)
        input_payload = clean({
            "name": name,
            "projectId": project_id,
            "description": description,
            "targetDate": target_date,
            "sortOrder": sort_order,
        })
        if id:
            return run_tool(
                "save_milestone (update)", params,
                lambda: client.request(queries.MILESTONE_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("projectMilestoneUpdate") or {}).get("projectMilestone") or {}).get("name", "?"),
            )
        if not name or not project_id:
            raise ValueError("save_milestone: `name` and `project_id` required to create")
        return run_tool(
            "save_milestone (create)", params,
            lambda: client.request(queries.MILESTONE_CREATE, {"input": input_payload}),
            lambda r: ((r.get("projectMilestoneCreate") or {}).get("projectMilestone") or {}).get("name", "?"),
        )
