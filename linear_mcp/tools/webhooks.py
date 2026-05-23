"""Webhook subscriptions: list / get / create / update / delete.

Linear webhooks are how external systems subscribe to events (Issue,
Comment, Project, Cycle, IssueLabel, ProjectUpdate, Reaction, User). This
module wires the GraphQL surface so an agent can spin up an event
subscription without leaving the MCP.

`delete_webhook` is destructive and uses the draft+confirm pattern.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ..drafts import STORE
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_webhooks(workspace: str | None = None, first: int = 50,
                      after: str | None = None) -> dict[str, Any]:
        """List webhooks configured for the workspace."""
        params = {"workspace": workspace, "first": first, "after": after}
        return run_tool(
            "list_webhooks", params,
            lambda: client_for(workspace).request(
                queries.LIST_WEBHOOKS, {"first": first, "after": after}
            ),
            lambda r: page_summary(r, "webhooks"),
        )

    @mcp.tool()
    def get_webhook(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a webhook by UUID."""
        return run_tool(
            "get_webhook", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_WEBHOOK, {"id": id}),
            lambda r: ((r.get("webhook") or {}).get("label") or "missing"),
        )

    @mcp.tool()
    def create_webhook(url: str, workspace: str | None = None,
                       resource_types: list[str] | None = None,
                       team_id: str | None = None,
                       label: str | None = None,
                       secret: str | None = None,
                       enabled: bool = True,
                       all_public_teams: bool = False) -> dict[str, Any]:
        """Create a webhook subscription.

        `url` is your HTTPS receiver. `resource_types` defaults to
        `["Issue", "Comment", "IssueLabel"]` if omitted — adjust as
        needed (full list at linear.app/developers/webhooks). `team_id`
        scopes to one team; `all_public_teams=True` subscribes to every
        public team in the org. `secret` is your HMAC signing secret —
        Linear adds it to the `Linear-Signature` header on every event.
        """
        rtypes = resource_types or ["Issue", "Comment", "IssueLabel"]
        params = {"workspace": workspace, "url": url, "resource_types": rtypes,
                  "team_id": team_id, "label": label, "enabled": enabled,
                  "all_public_teams": all_public_teams}
        input_payload = clean({
            "url": url,
            "resourceTypes": rtypes,
            "teamId": team_id,
            "label": label,
            "secret": secret,
            "enabled": enabled,
            "allPublicTeams": all_public_teams,
        })
        return run_tool(
            "create_webhook", params,
            lambda: client_for(workspace).request(
                queries.WEBHOOK_CREATE, {"input": input_payload}
            ),
            lambda r: ((r.get("webhookCreate") or {}).get("webhook") or {}).get("id", "?"),
        )

    @mcp.tool()
    def update_webhook(id: str, workspace: str | None = None,
                       url: str | None = None,
                       resource_types: list[str] | None = None,
                       label: str | None = None,
                       enabled: bool | None = None,
                       all_public_teams: bool | None = None) -> dict[str, Any]:
        """Update an existing webhook by UUID."""
        params = {"workspace": workspace, "id": id, "url": url,
                  "resource_types": resource_types, "label": label,
                  "enabled": enabled, "all_public_teams": all_public_teams}
        input_payload = clean({
            "url": url,
            "resourceTypes": resource_types,
            "label": label,
            "enabled": enabled,
            "allPublicTeams": all_public_teams,
        })
        return run_tool(
            "update_webhook", params,
            lambda: client_for(workspace).request(
                queries.WEBHOOK_UPDATE, {"id": id, "input": input_payload}
            ),
            lambda r: ((r.get("webhookUpdate") or {}).get("webhook") or {}).get("id", "?"),
        )

    @mcp.tool()
    def delete_webhook(id: str, workspace: str | None = None,
                       confirm_draft_id: str | None = None) -> dict[str, Any]:
        """Delete a webhook. Destructive — uses draft+confirm.

        Two-call flow:

        1. `delete_webhook(id=...)` returns a `draft_id` plus a preview
           of which webhook is about to go away.
        2. `delete_webhook(id=..., confirm_draft_id=<draft_id>)`
           actually issues `webhookDelete` against Linear.

        Drafts expire after 1 hour (override with
        `LINEAR_MCP_DRAFT_TTL_SECONDS`).
        """
        ws_alias = client_for(workspace).workspace.alias
        params = {"workspace": workspace, "id": id, "confirm_draft_id": confirm_draft_id}

        if confirm_draft_id:
            def _confirm() -> dict[str, Any]:
                draft = STORE.confirm(confirm_draft_id)
                if draft.kind != "delete_webhook" or draft.target_id != id:
                    raise ValueError(
                        f"draft {confirm_draft_id} does not match: kind={draft.kind} target={draft.target_id}"
                    )
                return client_for(workspace).request(queries.WEBHOOK_DELETE, {"id": id})
            return run_tool(
                "delete_webhook (confirm)", params, _confirm,
                lambda r: "deleted" if (r.get("webhookDelete") or {}).get("success") else "failed",
            )

        # Stage the draft: fetch webhook info so the preview is meaningful.
        def _stage() -> dict[str, Any]:
            client = client_for(workspace)
            current = client.request(queries.GET_WEBHOOK, {"id": id}).get("webhook") or {}
            if not current:
                raise ValueError(f"webhook {id} not found in workspace {ws_alias}")
            draft = STORE.create(
                workspace=ws_alias,
                kind="delete_webhook",
                target_id=id,
                target_label=current.get("label") or current.get("url") or id,
                preview={
                    "before": {"webhook": current, "enabled": current.get("enabled")},
                    "after": {"deleted": True},
                },
            )
            return {
                "draft_id": draft.draft_id,
                "preview": draft.preview,
                "expires_at": draft.expires_at(),
                "next_step": (
                    f"call delete_webhook(id='{id}', confirm_draft_id='{draft.draft_id}') "
                    "to commit deletion."
                ),
            }
        return run_tool("delete_webhook (stage)", params, _stage,
                        lambda r: f"draft {r.get('draft_id', '?')[:8]}…")
