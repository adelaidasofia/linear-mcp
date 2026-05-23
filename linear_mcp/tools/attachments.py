"""Attachments: list on issue / list by URL / get / link URL / delete.

Attachments are how Linear connects an issue to external context: a
Slack thread, a GitHub PR, a Figma file, a Sentry alert. v0.2 exposes
the URL-linking flow (`attachmentLinkURL`) — the rich
service-specific links (Slack, GitHub PR, Jira, etc.) live behind
their own integration mutations and are deferred to v0.3.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ..drafts import STORE
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_attachments(issue_id: str, workspace: str | None = None,
                         first: int = 50, after: str | None = None) -> dict[str, Any]:
        """List attachments on one issue."""
        params = {"workspace": workspace, "issue_id": issue_id, "first": first, "after": after}
        return run_tool(
            "list_attachments", params,
            lambda: client_for(workspace).request(
                queries.LIST_ATTACHMENTS_FOR_ISSUE,
                {"issue_id": issue_id, "first": first, "after": after},
            ),
            lambda r: page_summary(r, "attachments"),
        )

    @mcp.tool()
    def attachments_for_url(url: str, workspace: str | None = None,
                            first: int = 25) -> dict[str, Any]:
        """Reverse lookup: every attachment record across the workspace
        pointing at this URL. Useful to find which issue references a
        given Slack thread / PR / external doc.
        """
        params = {"workspace": workspace, "url": url, "first": first}
        return run_tool(
            "attachments_for_url", params,
            lambda: client_for(workspace).request(
                queries.ATTACHMENTS_FOR_URL, {"url": url, "first": first}
            ),
            lambda r: f"{len((r.get('attachmentsForURL') or {}).get('nodes') or [])} found",
        )

    @mcp.tool()
    def get_attachment(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get one attachment by UUID."""
        return run_tool(
            "get_attachment", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_ATTACHMENT, {"id": id}),
            lambda r: ((r.get("attachment") or {}).get("title") or "missing"),
        )

    @mcp.tool()
    def link_url_to_issue(issue_id: str, url: str,
                          workspace: str | None = None,
                          title: str | None = None,
                          icon_url: str | None = None) -> dict[str, Any]:
        """Attach an arbitrary URL to an issue.

        Linear renders the link in the issue sidebar. Pass `title` and
        `icon_url` to customize the display; otherwise Linear fetches
        OpenGraph metadata from the URL.
        """
        params = {"workspace": workspace, "issue_id": issue_id, "url": url,
                  "title": title, "icon_url": icon_url}
        return run_tool(
            "link_url_to_issue", params,
            lambda: client_for(workspace).request(
                queries.ATTACHMENT_LINK_URL,
                {"issueId": issue_id, "url": url, "title": title, "iconUrl": icon_url},
            ),
            lambda r: ((r.get("attachmentLinkURL") or {}).get("attachment") or {}).get("id", "?"),
        )

    @mcp.tool()
    def delete_attachment(id: str, workspace: str | None = None,
                          confirm_draft_id: str | None = None) -> dict[str, Any]:
        """Delete an attachment. Destructive — uses draft+confirm.

        Two-call flow identical to `delete_webhook`. The first call
        returns a draft_id + preview of the attachment that will be
        removed; the second call (with `confirm_draft_id`) commits.
        """
        ws_alias = client_for(workspace).workspace.alias
        params = {"workspace": workspace, "id": id, "confirm_draft_id": confirm_draft_id}

        if confirm_draft_id:
            def _confirm() -> dict[str, Any]:
                draft = STORE.confirm(confirm_draft_id)
                if draft.kind != "delete_attachment" or draft.target_id != id:
                    raise ValueError(
                        f"draft {confirm_draft_id} does not match: kind={draft.kind} target={draft.target_id}"
                    )
                return client_for(workspace).request(queries.ATTACHMENT_DELETE, {"id": id})
            return run_tool(
                "delete_attachment (confirm)", params, _confirm,
                lambda r: "deleted" if (r.get("attachmentDelete") or {}).get("success") else "failed",
            )

        def _stage() -> dict[str, Any]:
            client = client_for(workspace)
            current = client.request(queries.GET_ATTACHMENT, {"id": id}).get("attachment") or {}
            if not current:
                raise ValueError(f"attachment {id} not found in workspace {ws_alias}")
            draft = STORE.create(
                workspace=ws_alias,
                kind="delete_attachment",
                target_id=id,
                target_label=current.get("title") or current.get("url") or id,
                preview={
                    "before": {"attachment": current},
                    "after": {"deleted": True},
                },
            )
            return {
                "draft_id": draft.draft_id,
                "preview": draft.preview,
                "expires_at": draft.expires_at(),
                "next_step": (
                    f"call delete_attachment(id='{id}', confirm_draft_id='{draft.draft_id}') "
                    "to commit deletion."
                ),
            }
        return run_tool("delete_attachment (stage)", params, _stage,
                        lambda r: f"draft {r.get('draft_id', '?')[:8]}…")
