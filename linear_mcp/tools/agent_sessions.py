"""Agent sessions: list / get / create on issue / create on comment.

Linear shipped first-class agent sessions in 2025. An agent session is
a tracked run of an external agent against an issue or comment; Linear
renders the session inline with status (started / running / completed
/ failed) and links back to the agent's external dashboard.

This MCP creates the session record on Linear's side; the actual
agent execution still happens in whatever harness the operator runs.
Linear's docs at linear.app/developers/agents have the full
specification.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def register(mcp) -> None:
    @mcp.tool()
    def list_agent_sessions(workspace: str | None = None, first: int = 50,
                            after: str | None = None,
                            issue_id: str | None = None) -> dict[str, Any]:
        """List agent sessions. `issue_id` scopes to one issue."""
        params = {"workspace": workspace, "first": first, "after": after,
                  "issue_id": issue_id}
        variables: dict[str, Any] = {"first": first, "after": after}
        if issue_id:
            variables["filter"] = {"issue": {"id": {"eq": issue_id}}}
        return run_tool(
            "list_agent_sessions", params,
            lambda: client_for(workspace).request(queries.LIST_AGENT_SESSIONS, variables),
            lambda r: page_summary(r, "agentSessions"),
        )

    @mcp.tool()
    def get_agent_session(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get an agent session by UUID."""
        return run_tool(
            "get_agent_session", {"workspace": workspace, "id": id},
            lambda: client_for(workspace).request(queries.GET_AGENT_SESSION, {"id": id}),
            lambda r: ((r.get("agentSession") or {}).get("status") or "missing"),
        )

    @mcp.tool()
    def create_agent_session_on_issue(issue_id: str,
                                      workspace: str | None = None,
                                      session_type: str = "comment",
                                      external_url: str | None = None) -> dict[str, Any]:
        """Open an agent session attached to an issue.

        `session_type` is one of `comment` (the agent posts a comment as
        its output) or `commentThread` (the agent threads under existing
        comments). `external_url` lets the agent surface a link back to
        its own dashboard / run log.
        """
        params = {"workspace": workspace, "issue_id": issue_id,
                  "session_type": session_type, "external_url": external_url}
        input_payload = clean({
            "issueId": issue_id,
            "type": session_type,
            "externalUrl": external_url,
        })
        return run_tool(
            "create_agent_session_on_issue", params,
            lambda: client_for(workspace).request(
                queries.AGENT_SESSION_CREATE_ON_ISSUE, {"input": input_payload}
            ),
            lambda r: ((r.get("agentSessionCreateOnIssue") or {}).get("agentSession") or {}).get("id", "?"),
        )

    @mcp.tool()
    def create_agent_session_on_comment(comment_id: str,
                                        workspace: str | None = None,
                                        external_url: str | None = None) -> dict[str, Any]:
        """Open an agent session attached to a comment (typically a
        @mention of the agent app user)."""
        params = {"workspace": workspace, "comment_id": comment_id,
                  "external_url": external_url}
        input_payload = clean({
            "commentId": comment_id,
            "externalUrl": external_url,
        })
        return run_tool(
            "create_agent_session_on_comment", params,
            lambda: client_for(workspace).request(
                queries.AGENT_SESSION_CREATE_ON_COMMENT, {"input": input_payload}
            ),
            lambda r: ((r.get("agentSessionCreateOnComment") or {}).get("agentSession") or {}).get("id", "?"),
        )
