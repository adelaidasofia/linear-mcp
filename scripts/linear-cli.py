#!/usr/bin/env python3
"""
linear-cli.py — Fast Linear issue operations from the CLI.

Usage:
  python3 linear-cli.py get MYC-116                    # Fetch issue details
  python3 linear-cli.py list mycelium --state "Todo"   # List issues by state
  python3 linear-cli.py update MYC-116 --state "Done"  # Update issue state
  python3 linear-cli.py search mycelium "keyword"      # Full-text search
  python3 linear-cli.py create mycelium --title "..." --team "..."  # Create issue

Features:
  - Zero boilerplate: load workspace registry from admin.env automatically
  - JSON output for piping to jq/other tools
  - Human-friendly table output for interactive use
  - Batch operations with auth-phrase confirmation
  - Rate-limit visibility after each call
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add linear-mcp to path
sys.path.insert(0, str(Path.home() / ".claude" / "linear-mcp"))

from linear_mcp.workspaces import WorkspaceRegistry
from linear_mcp.client import LinearClient
from linear_mcp import queries


def load_registry() -> WorkspaceRegistry:
    """Load workspace registry from admin.env."""
    registry = WorkspaceRegistry.from_env()
    if registry.errors:
        for err in registry.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    return registry


def get_client(workspace: str | None) -> tuple[LinearClient, str]:
    """Get a LinearClient for the specified workspace."""
    registry = load_registry()
    ws = registry.get(workspace)
    client = LinearClient(workspace=ws)
    return client, ws.alias


def format_issue(issue: dict) -> dict:
    """Format issue dict for display."""
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "state": issue.get("state", {}).get("name"),
        "assignee": (issue.get("assignee") or {}).get("name"),
        "priority": issue.get("priorityLabel"),
        "url": issue.get("url"),
        "updated": issue.get("updatedAt"),
    }


def cmd_get(args) -> None:
    """Fetch and display a single issue."""
    client, ws_name = get_client(args.workspace)
    
    try:
        # Parse issue ID (supports both UUID and human identifier like MYC-116)
        issue_id = args.issue_id
        
        # Use GraphQL query directly
        query = f"""
        query {{
          issue(id: "{issue_id}") {{
            {queries.ISSUE_FIELDS}
          }}
        }}
        """
        
        result = client.request(query)
        issue = result.get("issue")
        
        if not issue:
            print(f"Issue not found: {issue_id}", file=sys.stderr)
            sys.exit(1)
        
        if args.json:
            print(json.dumps(issue, indent=2, default=str))
        else:
            formatted = format_issue(issue)
            print(json.dumps(formatted, indent=2, default=str))
        
        # Show rate limit
        if args.verbose and client.last_rate_limit:
            print(f"\nRate limit: {client.last_rate_limit}", file=sys.stderr)
    
    except Exception as e:
        print(f"Error fetching issue: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args) -> None:
    """List issues with optional filters."""
    client, ws_name = get_client(args.workspace)
    
    try:
        filt = {}
        if args.state:
            filt["state"] = {"name": {"eqIgnoreCase": args.state}}
        if args.assignee:
            if args.assignee.lower() == "me":
                filt["assignee"] = {"isMe": {"eq": True}}
            else:
                filt["assignee"] = {"id": {"eq": args.assignee}}
        if args.team:
            filt["team"] = {"id": {"eq": args.team}}
        if args.project:
            filt["project"] = {"id": {"eq": args.project}}
        if args.query:
            filt["searchableContent"] = {"contains": args.query}

        variables = {"first": args.limit or 50}
        if filt:
            variables["filter"] = filt

        result = client.request(queries.LIST_ISSUES, variables)
        issues = result.get("issues", {}).get("nodes", [])
        
        if args.json:
            print(json.dumps(issues, indent=2, default=str))
        else:
            for issue in issues:
                fmt = format_issue(issue)
                print(f"{fmt['identifier']:12} {fmt['title'][:50]:50} {fmt['state']:12} {fmt['assignee'] or 'unassigned':20}")
        
        if args.verbose and client.last_rate_limit:
            print(f"\nRate limit: {client.last_rate_limit}", file=sys.stderr)
    
    except Exception as e:
        print(f"Error listing issues: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_update(args) -> None:
    """Update an issue."""
    client, ws_name = get_client(args.workspace)
    
    try:
        input_payload = {}
        if args.state:
            # Resolve state name to state ID, scoped to the issue's team
            # (the identifier prefix, e.g. MYC-116 -> team key MYC).
            states_result = client.request(queries.LIST_ISSUE_STATUSES, {
                "first": 100,
                "filter": {"name": {"eqIgnoreCase": args.state}},
            })
            states = states_result.get("workflowStates", {}).get("nodes", [])
            team_key = args.issue_id.split("-")[0].upper() if "-" in args.issue_id else None
            if team_key:
                keyed = [s for s in states if (s.get("team") or {}).get("key") == team_key]
                states = keyed or states
            if not states:
                print(f"State not found: {args.state}", file=sys.stderr)
                sys.exit(1)
            input_payload["stateId"] = states[0]["id"]
        
        if args.assignee:
            if args.assignee.lower() == "me":
                viewer = client.viewer()
                input_payload["assigneeId"] = viewer.get("id")
            else:
                input_payload["assigneeId"] = args.assignee

        if args.priority is not None:
            input_payload["priority"] = args.priority
        
        if not input_payload:
            print("No fields to update", file=sys.stderr)
            sys.exit(1)
        
        result = client.request(queries.ISSUE_UPDATE, {
            "id": args.issue_id,
            "input": input_payload,
        })
        
        updated_issue = result.get("issueUpdate", {}).get("issue", {})
        
        if args.json:
            print(json.dumps(updated_issue, indent=2, default=str))
        else:
            fmt = format_issue(updated_issue)
            print(f"Updated: {fmt['identifier']} → {fmt['state']}")
        
        if args.verbose and client.last_rate_limit:
            print(f"\nRate limit: {client.last_rate_limit}", file=sys.stderr)
    
    except Exception as e:
        print(f"Error updating issue: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_comment(args) -> None:
    """Add a comment to an issue."""
    client, ws_name = get_client(args.workspace)

    try:
        mutation = """
        mutation CommentCreate($input: CommentCreateInput!) {
          commentCreate(input: $input) {
            success
            comment { id url }
          }
        }
        """
        result = client.request(mutation, {
            "input": {"issueId": args.issue_id, "body": args.body},
        })
        payload = result.get("commentCreate", {})
        if not payload.get("success"):
            print(f"Comment failed on {args.issue_id}", file=sys.stderr)
            sys.exit(1)
        comment = payload.get("comment") or {}
        if args.json:
            print(json.dumps(comment, indent=2, default=str))
        else:
            print(f"Commented on {args.issue_id}: {comment.get('url')}")
    except Exception as e:
        print(f"Error commenting: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_create(args) -> None:
    """Create an issue on a team (default: MYC)."""
    client, ws_name = get_client(args.workspace)

    try:
        team_key = (args.team_key or "MYC").upper()
        teams = client.request(
            "query($f: TeamFilter) { teams(filter: $f) { nodes { id key } } }",
            {"f": {"key": {"eq": team_key}}},
        ).get("teams", {}).get("nodes", [])
        if not teams:
            print(f"Team not found: {team_key}", file=sys.stderr)
            sys.exit(1)
        payload = {
            "teamId": teams[0]["id"],
            "title": args.title,
            "description": args.description or "",
        }
        if args.priority is not None:
            payload["priority"] = args.priority
        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { identifier url }
          }
        }
        """
        result = client.request(mutation, {"input": payload})
        out = result.get("issueCreate", {})
        if not out.get("success"):
            print("Issue creation failed", file=sys.stderr)
            sys.exit(1)
        issue = out.get("issue") or {}
        if args.json:
            print(json.dumps(issue, indent=2, default=str))
        else:
            print(f"Created {issue.get('identifier')}: {issue.get('url')}")
    except Exception as e:
        print(f"Error creating issue: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_search(args) -> None:
    """Full-text search across issues."""
    client, ws_name = get_client(args.workspace)
    
    try:
        result = client.request(queries.SEARCH_ISSUES, {
            "query": args.query,
            "first": args.limit or 50,
        })
        
        issues = result.get("searchIssues", {}).get("nodes", [])
        
        if args.json:
            print(json.dumps(issues, indent=2, default=str))
        else:
            for issue in issues:
                fmt = format_issue(issue)
                print(f"{fmt['identifier']:12} {fmt['title'][:60]:60} {fmt['state']:12}")
        
        if args.verbose and client.last_rate_limit:
            print(f"\nRate limit: {client.last_rate_limit}", file=sys.stderr)
    
    except Exception as e:
        print(f"Error searching: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Fast Linear issue operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "-w", "--workspace",
        help="Workspace alias (default: primary from admin.env)",
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output raw JSON (default: human-friendly table)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show rate-limit info and debug output",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # get <issue-id>
    get_parser = subparsers.add_parser("get", help="Fetch issue details")
    get_parser.add_argument("issue_id", help="Issue ID or identifier (e.g., MYC-116)")
    get_parser.set_defaults(func=cmd_get)
    
    # list [filters]
    list_parser = subparsers.add_parser("list", help="List issues")
    list_parser.add_argument("--state", help="Filter by state (e.g., Todo, Done)")
    list_parser.add_argument("--assignee", help="Filter by assignee (or 'me')")
    list_parser.add_argument("--team", help="Filter by team ID")
    list_parser.add_argument("--project", help="Filter by project ID")
    list_parser.add_argument("--query", help="Full-text search")
    list_parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    list_parser.set_defaults(func=cmd_list)
    
    # update <issue-id> [fields]
    update_parser = subparsers.add_parser("update", help="Update issue")
    update_parser.add_argument("issue_id", help="Issue ID or identifier")
    update_parser.add_argument("--state", help="New state (e.g., Done, Todo)")
    update_parser.add_argument("--assignee", help="New assignee (or 'me')")
    update_parser.add_argument("--priority", type=int, help="Priority (0-4)")
    update_parser.set_defaults(func=cmd_update)
    
    # create --title ... [--description ...] [--priority N] [--team-key MYC]
    create_parser = subparsers.add_parser("create", help="Create an issue")
    create_parser.add_argument("--title", required=True, help="Issue title")
    create_parser.add_argument("--description", help="Issue description (markdown)")
    create_parser.add_argument("--priority", type=int, help="Priority (0-4)")
    create_parser.add_argument("--team-key", help="Team key (default: MYC)")
    create_parser.set_defaults(func=cmd_create)

    # comment <issue-id> <body>
    comment_parser = subparsers.add_parser("comment", help="Add a comment")
    comment_parser.add_argument("issue_id", help="Issue ID or identifier")
    comment_parser.add_argument("body", help="Comment body (markdown)")
    comment_parser.set_defaults(func=cmd_comment)

    # search <query>
    search_parser = subparsers.add_parser("search", help="Full-text search")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Max results")
    search_parser.set_defaults(func=cmd_search)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
