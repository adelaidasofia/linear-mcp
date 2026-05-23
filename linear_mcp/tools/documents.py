"""list_documents + get_document + save_document."""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_documents(workspace: str | None = None, first: int = 50,
                       after: str | None = None) -> dict[str, Any]:
        """List documents in the workspace."""
        params = {"workspace": workspace, "first": first, "after": after}
        return run_tool(
            "list_documents", params,
            lambda: client_for(workspace).request(
                queries.LIST_DOCUMENTS, {"first": first, "after": after}
            ),
            lambda r: page_summary(r, "documents"),
        )

    @mcp.tool()
    def get_document(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a document by UUID."""
        return run_tool(
            "get_document", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_DOCUMENT, {"id": id}),
            lambda r: ((r.get("document") or {}).get("title") or "missing"),
        )

    @mcp.tool()
    def save_document(workspace: str | None = None,
                      id: str | None = None,
                      title: str | None = None,
                      content: str | None = None,
                      project_id: str | None = None,
                      initiative_id: str | None = None,
                      icon: str | None = None,
                      color: str | None = None) -> dict[str, Any]:
        """Create or update a document.

        Pass `id` to update. Creating requires `title` and one of
        `project_id` or `initiative_id` (documents attach to a project or
        initiative in Linear's model).
        """
        params = {
            "workspace": workspace, "id": id, "title": title, "project_id": project_id,
            "initiative_id": initiative_id, "icon": icon, "color": color,
        }
        client = client_for(workspace)
        input_payload = clean({
            "title": title,
            "content": content,
            "projectId": project_id,
            "initiativeId": initiative_id,
            "icon": icon,
            "color": color,
        })
        if id:
            return run_tool(
                "save_document (update)", params,
                lambda: client.request(queries.DOCUMENT_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("documentUpdate") or {}).get("document") or {}).get("title", "?"),
            )
        if not title or not (project_id or initiative_id):
            raise ValueError(
                "save_document: `title` and one of `project_id`/`initiative_id` required to create"
            )
        return run_tool(
            "save_document (create)", params,
            lambda: client.request(queries.DOCUMENT_CREATE, {"input": input_payload}),
            lambda r: ((r.get("documentCreate") or {}).get("document") or {}).get("title", "?"),
        )
