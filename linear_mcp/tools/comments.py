"""list_comments + save_comment."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_comments(workspace: str | None = None, first: int = 50,
                      after: str | None = None,
                      issue_id: str | None = None,
                      project_id: str | None = None) -> dict[str, Any]:
        """List comments. Scope by `issue_id` or `project_id`."""
        params = {"workspace": workspace, "first": first, "after": after,
                  "issue_id": issue_id, "project_id": project_id}
        f: dict[str, Any] = {}
        if issue_id:
            f["issue"] = {"id": {"eq": issue_id}}
        if project_id:
            f["project"] = {"id": {"eq": project_id}}
        variables: dict[str, Any] = {"first": first, "after": after}
        if f:
            variables["filter"] = f
        return run_tool(
            "list_comments", params,
            lambda: client_for(workspace).request(queries.LIST_COMMENTS, variables),
            lambda r: page_summary(r, "comments"),
        )

    @mcp.tool()
    def save_comment(workspace: str | None = None,
                     id: str | None = None,
                     body: str | None = None,
                     issue_id: str | None = None,
                     project_id: str | None = None,
                     parent_id: str | None = None) -> dict[str, Any]:
        """Create or update a comment.

        Pass `id` to edit an existing comment (only `body` is updateable).
        Creating requires `body` and either `issue_id` or `project_id`.
        `parent_id` threads the comment as a reply.
        """
        params = {
            "workspace": workspace, "id": id, "issue_id": issue_id,
            "project_id": project_id, "parent_id": parent_id,
        }
        client = client_for(workspace)
        if id:
            input_payload = clean({"body": body})
            return run_tool(
                "save_comment (update)", params,
                lambda: client.request(queries.COMMENT_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("commentUpdate") or {}).get("comment") or {}).get("id", "?"),
            )
        if not body:
            raise ValueError("save_comment: `body` required to create a new comment")
        if not (issue_id or project_id):
            raise ValueError("save_comment: `issue_id` or `project_id` required to create")
        input_payload = clean({
            "body": body,
            "issueId": issue_id,
            "projectId": project_id,
            "parentId": parent_id,
        })
        return run_tool(
            "save_comment (create)", params,
            lambda: client.request(queries.COMMENT_CREATE, {"input": input_payload}),
            lambda r: ((r.get("commentCreate") or {}).get("comment") or {}).get("id", "?"),
        )
