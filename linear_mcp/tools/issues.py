"""list_issues + get_issue + save_issue.

Issue filters accept the most common axes (team, assignee, state, project,
text). The full Linear IssueFilter is rich; pass `filter` directly to drop
to the raw shape when needed.
"""

from __future__ import annotations

from typing import Any

from .. import queries
from ._common import client_for, clean, run_tool, page_summary


def _build_issue_filter(assignee_id: str | None, team_id: str | None,
                       project_id: str | None, state_name: str | None,
                       state_type: str | None, query: str | None,
                       extra: dict | None) -> dict:
    f: dict[str, Any] = {}
    if assignee_id:
        if assignee_id.lower() == "me":
            f["assignee"] = {"isMe": {"eq": True}}
        else:
            f["assignee"] = {"id": {"eq": assignee_id}}
    if team_id:
        f["team"] = {"id": {"eq": team_id}}
    if project_id:
        f["project"] = {"id": {"eq": project_id}}
    if state_name:
        f["state"] = {"name": {"eqIgnoreCase": state_name}}
    if state_type:
        f.setdefault("state", {})["type"] = {"eq": state_type}
    if query:
        # Linear supports a top-level `searchableContent` filter on Issue.
        f["searchableContent"] = {"contains": query}
    if extra:
        f.update(extra)
    return f


def register(mcp) -> None:
    @mcp.tool()
    def list_issues(workspace: str | None = None, first: int = 50,
                    after: str | None = None,
                    assignee_id: str | None = None,
                    team_id: str | None = None,
                    project_id: str | None = None,
                    state_name: str | None = None,
                    state_type: str | None = None,
                    query: str | None = None,
                    filter: dict | None = None,
                    order_by: str = "updatedAt") -> dict[str, Any]:
        """List issues with common filters.

        `assignee_id` accepts a user UUID or the literal `me`. `state_type`
        accepts one of: backlog, unstarted, started, completed, canceled,
        triage. `query` does a full-text search across title + description.
        `filter` lets you pass a raw Linear IssueFilter for cases the
        convenience args don't cover.

        `order_by` is `updatedAt` (default) or `createdAt`.
        """
        params = {
            "workspace": workspace, "first": first, "after": after,
            "assignee_id": assignee_id, "team_id": team_id, "project_id": project_id,
            "state_name": state_name, "state_type": state_type, "query": query,
            "order_by": order_by,
        }
        variables: dict[str, Any] = {
            "first": first, "after": after, "orderBy": order_by,
        }
        f = _build_issue_filter(
            assignee_id, team_id, project_id, state_name, state_type, query, filter
        )
        if f:
            variables["filter"] = f
        return run_tool(
            "list_issues", params,
            lambda: client_for(workspace).request(queries.LIST_ISSUES, variables),
            lambda r: page_summary(r, "issues"),
        )

    @mcp.tool()
    def get_issue(id: str, workspace: str | None = None) -> dict[str, Any]:
        """Get a single issue.

        `id` accepts either the UUID or the human identifier (e.g.
        `ONDE-123`). When given an identifier, the tool resolves it through
        a one-shot search.
        """
        params = {"workspace": workspace, "id": id}
        client = client_for(workspace)

        def _run() -> dict:
            if "-" in id and not _looks_like_uuid(id):
                team_key, _, number = id.partition("-")
                if not number.isdigit():
                    raise ValueError(f"unrecognized issue id: {id}")
                resp = client.request(
                    queries.GET_ISSUE_BY_IDENTIFIER,
                    {"team": team_key.upper(), "number": float(number)},
                )
                nodes = (resp.get("issues") or {}).get("nodes") or []
                if not nodes:
                    return {"issue": None}
                return {"issue": nodes[0]}
            return client.request(queries.GET_ISSUE, {"id": id})

        return run_tool(
            "get_issue", params, _run,
            lambda r: ((r.get("issue") or {}).get("identifier") or "missing"),
        )

    @mcp.tool()
    def save_issue(workspace: str | None = None,
                   id: str | None = None,
                   title: str | None = None,
                   description: str | None = None,
                   team_id: str | None = None,
                   assignee_id: str | None = None,
                   state_id: str | None = None,
                   project_id: str | None = None,
                   project_milestone_id: str | None = None,
                   cycle_id: str | None = None,
                   parent_id: str | None = None,
                   priority: int | None = None,
                   estimate: int | None = None,
                   label_ids: list[str] | None = None,
                   due_date: str | None = None) -> dict[str, Any]:
        """Create or update an issue.

        Pass `id` to update. Creating requires `title` and `team_id`.
        `assignee_id` accepts a UUID or `me`. `priority` is 0-4
        (0=none, 1=urgent, 2=high, 3=medium, 4=low).
        """
        params = {
            "workspace": workspace, "id": id, "title": title, "team_id": team_id,
            "assignee_id": assignee_id, "state_id": state_id, "project_id": project_id,
            "project_milestone_id": project_milestone_id, "cycle_id": cycle_id,
            "parent_id": parent_id, "priority": priority, "estimate": estimate,
            "label_ids": label_ids, "due_date": due_date,
        }
        client = client_for(workspace)
        resolved_assignee = assignee_id
        if assignee_id and assignee_id.lower() == "me":
            resolved_assignee = (client.viewer().get("id") or "").strip() or None
        input_payload = clean({
            "title": title,
            "description": description,
            "teamId": team_id,
            "assigneeId": resolved_assignee,
            "stateId": state_id,
            "projectId": project_id,
            "projectMilestoneId": project_milestone_id,
            "cycleId": cycle_id,
            "parentId": parent_id,
            "priority": priority,
            "estimate": estimate,
            "labelIds": label_ids,
            "dueDate": due_date,
        })
        if id:
            return run_tool(
                "save_issue (update)", params,
                lambda: client.request(queries.ISSUE_UPDATE, {"id": id, "input": input_payload}),
                lambda r: ((r.get("issueUpdate") or {}).get("issue") or {}).get("identifier", "?"),
            )
        if not title or not team_id:
            raise ValueError("save_issue: `title` and `team_id` required to create")
        return run_tool(
            "save_issue (create)", params,
            lambda: client.request(queries.ISSUE_CREATE, {"input": input_payload}),
            lambda r: ((r.get("issueCreate") or {}).get("issue") or {}).get("identifier", "?"),
        )


def _looks_like_uuid(s: str) -> bool:
    """Cheap UUID heuristic. 36 chars with hyphens at the right slots."""
    if len(s) != 36:
        return False
    return s[8] == "-" and s[13] == "-" and s[18] == "-" and s[23] == "-"
