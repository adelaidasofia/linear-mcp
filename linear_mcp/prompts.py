"""MCP prompts surfaced by linear-mcp.

Prompts are MCP's "canned workflow" primitive — they show up as
slash-style commands in the client UI and pre-fill the conversation
with a structured instruction. v0.2 ships three high-leverage ones:

  - triage-issue       — "what does this issue actually need, in order"
  - project-status     — "draft a weekly status update for project X"
  - inbox-sweep        — "summarize today's notifications + propose actions"

Each prompt returns a system + user message pair the client uses to
seed a fresh thread.
"""

from __future__ import annotations


def register(mcp) -> None:

    @mcp.prompt(name="triage-issue")
    def triage_issue(issue_id: str, workspace: str | None = None) -> str:
        """Triage a Linear issue: classify, assign, label, prioritize, link.

        Use this to standardize how an agent processes an incoming
        issue. The prompt pulls the issue + recent comments + relations
        so the agent can suggest concrete next moves rather than vague
        triage advice.
        """
        ws_clause = f"workspace='{workspace}'" if workspace else "primary workspace"
        return f"""You are triaging Linear issue {issue_id} in {ws_clause}.

Use these tools in sequence:

1. get_issue(id="{issue_id}"{f', workspace="{workspace}"' if workspace else ''}) — pull the issue
2. list_comments(issue_id="{issue_id}"{f', workspace="{workspace}"' if workspace else ''}) — pull every comment
3. list_issue_relations(issue_id="{issue_id}"{f', workspace="{workspace}"' if workspace else ''}) — pull blocks / duplicates / related
4. list_issue_statuses(team_id=<from issue>{f', workspace="{workspace}"' if workspace else ''}) — see the team's workflow states
5. list_issue_labels(team_id=<from issue>{f', workspace="{workspace}"' if workspace else ''}) — see available labels

Then produce, in this order:

- **One-line summary** of what the issue is actually asking for.
- **Classification**: bug / feature / question / chore / spike.
- **Suggested labels** (from the team's existing label set; do not invent).
- **Suggested state** (where in the workflow this belongs RIGHT NOW).
- **Suggested assignee** (from team membership; consider who owns the affected area).
- **Suggested priority** (0=none, 1=urgent, 2=high, 3=medium, 4=low) with reasoning.
- **Duplicate check**: does any related/recent issue already cover this?
- **Recommended next action**: the single concrete next step the assignee should take.

If you'd commit any of the above to Linear, propose the exact save_issue / create_issue_relation / save_comment call but do NOT execute until the operator confirms.
"""

    @mcp.prompt(name="project-status")
    def project_status(project_id: str, workspace: str | None = None) -> str:
        """Draft a weekly project status update from current Linear state."""
        ws_clause = f"workspace='{workspace}'" if workspace else "primary workspace"
        return f"""Draft a weekly status update for Linear project {project_id} in {ws_clause}.

Pull current state:

1. get_project(id="{project_id}"{f', workspace="{workspace}"' if workspace else ''}) — project shell + progress + dates
2. list_milestones(project_id="{project_id}"{f', workspace="{workspace}"' if workspace else ''}) — milestone landscape
3. list_issues(project_id="{project_id}", state_type="completed", first=50{f', workspace="{workspace}"' if workspace else ''}, order_by="updatedAt") — recent wins
4. list_issues(project_id="{project_id}", state_type="started", first=50{f', workspace="{workspace}"' if workspace else ''}) — work in flight
5. list_issues(project_id="{project_id}", state_type="backlog", first=20{f', workspace="{workspace}"' if workspace else ''}) — what's next up

Then write the status update in this exact shape:

```
# <Project name> — week of <Monday's date>

## Health
<onTrack | atRisk | offTrack> — <one-sentence rationale>

## Shipped this week
<bullet list of completed issues, identifier + one-line title>

## In flight
<bullet list of started issues, identifier + who owns it>

## Upcoming
<bullet list of next 3-5 issues queued up>

## Blockers / asks
<honest list; "none" only if there genuinely are none>
```

When the draft is ready, propose the exact save_status_update call so the operator can post it with one confirmation. Do not auto-post.
"""

    @mcp.prompt(name="inbox-sweep")
    def inbox_sweep(workspace: str | None = None) -> str:
        """Triage today's notification inbox — categorize, propose actions."""
        ws_clause = f"workspace='{workspace}'" if workspace else "primary workspace"
        return f"""Sweep the Linear notification inbox in {ws_clause}.

1. notifications_unread_count({f'workspace="{workspace}"' if workspace else ''}) — total volume
2. list_notifications(first=50, unread_only=true{f', workspace="{workspace}"' if workspace else ''}) — every unread item

Group the results into:

- **Need a reply now** — comment mentions, direct asks, blocked-on-you
- **FYI, no action needed** — status changes, assignment moves I just want to know about
- **Already handled elsewhere** — Slack/PR/email already covered this; safe to archive
- **Can defer** — read later

For each item that needs a reply, propose the exact save_comment / save_issue / link_url_to_issue call. For "already handled" items, propose archive_notification(id=...). Never auto-execute. Always show the operator the proposed action list and wait for go.
"""
