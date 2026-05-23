"""Inbox notifications: list / get / unread_count / mark_read / archive.

Linear's notification system is the inbox surface — every event the
viewer is subscribed to lands here. Useful for triage agents that fan
through "what needs my attention today."
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_notifications(workspace: str | None = None, first: int = 50,
                           after: str | None = None,
                           unread_only: bool = False) -> dict[str, Any]:
        """List notifications in the viewer's inbox.

        `unread_only=True` restricts to notifications with no `readAt`.
        Nodes carry `__typename` (IssueNotification, ProjectNotification,
        etc.) so an agent can branch on category.
        """
        params = {"workspace": workspace, "first": first, "after": after,
                  "unread_only": unread_only}
        variables: dict[str, Any] = {"first": first, "after": after}
        if unread_only:
            variables["filter"] = {"readAt": {"null": True}}
        return run_tool(
            "list_notifications", params,
            lambda: client_for(workspace).request(queries.LIST_NOTIFICATIONS, variables),
            lambda r: page_summary(r, "notifications"),
        )

    @mcp.tool()
    def get_notification(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get one notification by UUID."""
        return run_tool(
            "get_notification", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_NOTIFICATION, {"id": id}),
            lambda r: ((r.get("notification") or {}).get("__typename") or "missing"),
        )

    @mcp.tool()
    def notifications_unread_count(workspace: str | None = None) -> dict[str, Any]:
        """Return the count of unread notifications in the inbox."""
        params = {"workspace": workspace}
        return run_tool(
            "notifications_unread_count", params,
            lambda: client_for(workspace).request(queries.NOTIFICATIONS_UNREAD_COUNT),
            lambda r: str(r.get("notificationsUnreadCount", 0)),
        )

    @mcp.tool()
    def mark_notification_read(id: str, workspace: str | None = None,
                               read: bool = True) -> dict[str, Any]:
        """Mark a notification read (or unread by passing `read=False`)."""
        params = {"workspace": workspace, "id": id, "read": read}
        # Linear's NotificationUpdateInput accepts `readAt` (ISO timestamp
        # or null). Passing an empty string clears it.
        from datetime import datetime, timezone
        input_payload = {
            "readAt": datetime.now(timezone.utc).isoformat() if read else None
        }
        return run_tool(
            "mark_notification_read", params,
            lambda: client_for(workspace).request(
                queries.NOTIFICATION_MARK_READ, {"id": id, "input": input_payload}
            ),
            lambda r: "ok" if (r.get("notificationUpdate") or {}).get("success") else "failed",
        )

    @mcp.tool()
    def mark_all_notifications_read(workspace: str | None = None,
                                    category: str | None = None) -> dict[str, Any]:
        """Mark every notification in the inbox as read.

        `category` optionally scopes to one notification category
        (e.g. `triageResponsibility`, `assigned`).
        """
        params = {"workspace": workspace, "category": category}
        input_payload = clean({"botActor": None, "category": category})
        return run_tool(
            "mark_all_notifications_read", params,
            lambda: client_for(workspace).request(
                queries.NOTIFICATION_MARK_READ_ALL, {"input": input_payload or {}}
            ),
            lambda r: "ok" if (r.get("notificationMarkReadAll") or {}).get("success") else "failed",
        )

    @mcp.tool()
    def archive_notification(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Archive a notification (removes from inbox; reversible)."""
        params = {"workspace": workspace, "id": id}
        return run_tool(
            "archive_notification", params,
            lambda: client_for(workspace).request(queries.NOTIFICATION_ARCHIVE, {"id": id}),
            lambda r: "ok" if (r.get("notificationArchive") or {}).get("success") else "failed",
        )
