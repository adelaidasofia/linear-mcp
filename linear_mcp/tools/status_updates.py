"""save_status_update — post a project status update."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool


def register(mcp) -> None:
    @mcp.tool()
    def save_status_update(workspace: str | None = None,
                           project_id: str | None = None,
                           body: str | None = None,
                           health: str | None = None) -> dict[str, Any]:
        """Post a status update against a project.

        `health` is one of `onTrack`, `atRisk`, `offTrack` (Linear enums).
        `body` is markdown.
        """
        if not project_id or not body:
            raise ValueError("save_status_update: `project_id` and `body` required")
        params = {"workspace": workspace, "project_id": project_id, "health": health}
        input_payload = clean({
            "projectId": project_id,
            "body": body,
            "health": health,
        })
        return run_tool(
            "save_status_update", params,
            lambda: client_for(workspace).request(
                queries.PROJECT_UPDATE_CREATE, {"input": input_payload}
            ),
            lambda r: ((r.get("projectUpdateCreate") or {}).get("projectUpdate") or {}).get("id", "?"),
        )
