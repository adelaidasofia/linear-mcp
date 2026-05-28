"""Fast Linear issue execution preflight.

This CLI is intentionally narrower than the MCP server. It covers the
repeat workflow agents do before touching code:

1. Resolve the issue and workspace.
2. Check relation blockers.
3. Do a lightweight scope-overlap scan against same-project siblings.
4. Optionally move the issue to In Progress and create a dev worktree.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import queries
from .client import LinearClient
from .tools.relations import _merge_issue_relation_pages
from .workspaces import WorkspaceRegistry

WORKSPACE_BY_PREFIX = {
    "MYC": "mycelium",
    "ONDE": "onde",
}

KNOWN_REPOS = (
    "memory-runtime-pro",
    "mycelium-studio",
    "mycelium-site",
    "mycelium-vault",
    "linear-mcp",
    "ai-brain-starter",
    "growth-os-engine",
    "humanizer",
)

REPO_ALIASES = {
    "memory-runtime": "memory-runtime-pro",
    "runtime-pro": "memory-runtime-pro",
    "runtime pro": "memory-runtime-pro",
    "studio": "mycelium-studio",
    "mycelium studio": "mycelium-studio",
    "site": "mycelium-site",
    "website": "mycelium-site",
    "vault": "mycelium-vault",
}

TERMINAL_STATE_TYPES = {"completed", "canceled"}
CANDIDATE_STATE_TYPES = ("unstarted", "backlog", "triage")
WORKTREE_BIN = Path.home() / ".local" / "bin" / "claude-dev-worktree"


@dataclass(frozen=True)
class Candidate:
    issue: dict[str, Any]
    blockers: list[dict[str, Any]]


def parse_issue_identifier(value: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]{1,9})-(\d+)", value.strip())
    if not match:
        return None
    return match.group(1).upper(), int(match.group(2))


def infer_workspace(issue_ref: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    parsed = parse_issue_identifier(issue_ref)
    if not parsed:
        return None
    return WORKSPACE_BY_PREFIX.get(parsed[0])


def slugify(value: str, *, max_len: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug[:max_len].rstrip("-") or "linear-issue")


def worktree_slug(issue: dict[str, Any]) -> str:
    identifier = (issue.get("identifier") or "linear").lower()
    title = slugify(issue.get("title") or "issue", max_len=52)
    return slugify(f"{identifier}-{title}", max_len=72)


def load_registry() -> WorkspaceRegistry:
    registry = WorkspaceRegistry.from_env()
    if registry.errors:
        errors = "\n".join(f"- {error}" for error in registry.errors)
        raise RuntimeError(f"Linear workspace registry is not ready:\n{errors}")
    return registry


def client_for(workspace: str | None) -> LinearClient:
    registry = load_registry()
    return LinearClient(registry.get(workspace))


def resolve_issue(client: LinearClient, issue_ref: str) -> dict[str, Any]:
    parsed = parse_issue_identifier(issue_ref)
    if parsed:
        team_key, number = parsed
        data = client.request(
            queries.GET_ISSUE_BY_IDENTIFIER,
            {"team": team_key, "number": float(number)},
        )
        nodes = (data.get("issues") or {}).get("nodes") or []
        if nodes:
            return nodes[0]
        raise LookupError(f"issue not found: {issue_ref}")

    data = client.request(queries.GET_ISSUE, {"id": issue_ref})
    issue = data.get("issue")
    if issue:
        return issue
    raise LookupError(f"issue not found: {issue_ref}")


def fetch_issue_relations(client: LinearClient, issue_id: str) -> list[dict[str, Any]]:
    data = client.request(
        queries.GET_ISSUE_RELATIONS,
        {"id": issue_id, "first": 50, "after": None},
    )
    merged = _merge_issue_relation_pages(data)
    return (merged.get("issueRelations") or {}).get("nodes") or []


def relation_counterparty(
    relation: dict[str, Any],
    target_issue_id: str,
) -> dict[str, Any] | None:
    issue = relation.get("issue") or {}
    related = relation.get("relatedIssue") or {}
    if issue.get("id") == target_issue_id:
        return related
    if related.get("id") == target_issue_id:
        return issue
    return None


def incomplete_blockers(
    target_issue: dict[str, Any],
    relations: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return upstream blockers whose workflow state is not terminal.

    Linear relation semantics are directional for `blocks`: relation.issue
    blocks relation.relatedIssue. A target is blocked only when it is the
    relatedIssue side of that relation.
    """
    target_id = target_issue.get("id")
    blockers: list[dict[str, Any]] = []
    for relation in relations:
        if relation.get("type") != "blocks":
            continue
        issue = relation.get("issue") or {}
        related = relation.get("relatedIssue") or {}
        if related.get("id") != target_id:
            continue
        state_type = ((issue.get("state") or {}).get("type") or "").lower()
        if state_type not in TERMINAL_STATE_TYPES:
            blockers.append(issue)
    return blockers


def issue_text(issue: dict[str, Any]) -> str:
    labels = " ".join(
        label.get("name") or ""
        for label in ((issue.get("labels") or {}).get("nodes") or [])
    )
    return "\n".join(
        str(part or "")
        for part in (
            issue.get("identifier"),
            issue.get("title"),
            issue.get("description"),
            issue.get("branchName"),
            labels,
        )
    )


def scope_tokens(issue: dict[str, Any]) -> set[str]:
    text = issue_text(issue).lower()
    tokens: set[str] = set()
    path_pattern = re.compile(
        r"(?:^|[\s'\"`(])((?:[\w.~@-]+/)+[\w.@-]+\."
        r"(?:py|ts|tsx|js|jsx|md|json|toml|yaml|yml|css|scss|html|go|rs|rb|sh|sql))"
    )
    for match in path_pattern.finditer(text):
        tokens.add(match.group(1).strip(".,:;)]}"))
    for repo in KNOWN_REPOS:
        if repo in text:
            tokens.add(repo)
    for alias, repo in REPO_ALIASES.items():
        if alias in text:
            tokens.add(repo)
    branch = (issue.get("branchName") or "").lower()
    if branch:
        tokens.add(branch)
    return tokens


def scope_overlap_report(
    client: LinearClient,
    issue: dict[str, Any],
    *,
    first: int = 50,
) -> dict[str, Any]:
    project = issue.get("project") or {}
    project_id = project.get("id")
    if not project_id:
        return {"status": "skipped", "reason": "issue has no project"}

    target_tokens = scope_tokens(issue)
    if not target_tokens:
        return {
            "status": "clean",
            "project": project.get("name"),
            "tokens": [],
            "matches": [],
        }

    data = client.request(
        queries.LIST_ISSUES,
        {
            "first": first,
            "after": None,
            "orderBy": "updatedAt",
            "filter": {"project": {"id": {"eq": project_id}}},
        },
    )
    siblings = (data.get("issues") or {}).get("nodes") or []
    matches = []
    target_id = issue.get("id")
    for sibling in siblings:
        if sibling.get("id") == target_id:
            continue
        state_type = ((sibling.get("state") or {}).get("type") or "").lower()
        if state_type in TERMINAL_STATE_TYPES:
            continue
        overlap = sorted(target_tokens & scope_tokens(sibling))
        if overlap:
            matches.append({
                "identifier": sibling.get("identifier"),
                "title": sibling.get("title"),
                "state": (sibling.get("state") or {}).get("name"),
                "overlap": overlap,
            })

    return {
        "status": "overlap" if matches else "clean",
        "project": project.get("name"),
        "tokens": sorted(target_tokens),
        "matches": matches,
    }


def infer_repo(issue: dict[str, Any], explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    text = issue_text(issue).lower()
    for repo in KNOWN_REPOS:
        if repo in text:
            return repo
    for alias, repo in REPO_ALIASES.items():
        if alias in text:
            return repo
    return None


def find_started_state(client: LinearClient, team_id: str) -> dict[str, Any] | None:
    data = client.request(
        queries.LIST_ISSUE_STATUSES,
        {
            "first": 100,
            "after": None,
            "filter": {"team": {"id": {"eq": team_id}}},
        },
    )
    states = (data.get("workflowStates") or {}).get("nodes") or []
    exact = next(
        (
            state for state in states
            if (state.get("name") or "").strip().lower() == "in progress"
        ),
        None,
    )
    if exact:
        return exact
    return next(
        (
            state for state in states
            if ((state.get("type") or "").lower() == "started")
        ),
        None,
    )


def issue_summary(issue: dict[str, Any]) -> str:
    state = ((issue.get("state") or {}).get("name") or "?")
    return f"{issue.get('identifier')}: {issue.get('title')} [{state}]"


def update_issue_state(
    client: LinearClient,
    issue: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    data = client.request(
        queries.ISSUE_UPDATE,
        {"id": issue["id"], "input": {"stateId": state["id"]}},
    )
    return (data.get("issueUpdate") or {}).get("issue") or issue


def create_worktree(repo: str, slug: str) -> str:
    if not WORKTREE_BIN.exists():
        raise FileNotFoundError(f"worktree helper missing: {WORKTREE_BIN}")
    proc = subprocess.run(
        [str(WORKTREE_BIN), "start", repo, slug],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"worktree start failed: {detail}")
    return proc.stdout.strip().splitlines()[-1]


def list_candidate_issues(
    client: LinearClient,
    priority: int,
    *,
    first_per_state: int = 15,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    issues: list[dict[str, Any]] = []
    for state_type in CANDIDATE_STATE_TYPES:
        data = client.request(
            queries.LIST_ISSUES,
            {
                "first": first_per_state,
                "after": None,
                "orderBy": "updatedAt",
                "filter": {
                    "priority": {"eq": priority},
                    "state": {"type": {"eq": state_type}},
                },
            },
        )
        for issue in (data.get("issues") or {}).get("nodes") or []:
            issue_id = issue.get("id")
            if issue_id and issue_id not in seen:
                seen.add(issue_id)
                issues.append(issue)
    return issues


def parse_priority(value: str) -> int:
    raw = value.strip().lower()
    if raw.startswith("p"):
        raw = raw[1:]
    if not raw.isdigit():
        raise argparse.ArgumentTypeError("priority must look like p1, p2, or 1")
    priority = int(raw)
    if priority < 0 or priority > 4:
        raise argparse.ArgumentTypeError("Linear priority must be 0..4")
    return priority


def build_execute_report(
    client: LinearClient,
    issue_ref: str,
    *,
    repo: str | None,
) -> dict[str, Any]:
    viewer = client.viewer()
    issue = resolve_issue(client, issue_ref)
    relations = fetch_issue_relations(client, issue["id"])
    blockers = incomplete_blockers(issue, relations)
    overlap = scope_overlap_report(client, issue)
    chosen_repo = infer_repo(issue, repo)
    started_state = find_started_state(client, (issue.get("team") or {})["id"])
    return {
        "viewer": {
            "name": viewer.get("displayName") or viewer.get("name"),
            "organization": (viewer.get("organization") or {}).get("name"),
        },
        "issue": issue,
        "relations": {"count": len(relations), "blockers": blockers},
        "scope_overlap": overlap,
        "repo": chosen_repo,
        "worktree_slug": worktree_slug(issue),
        "started_state": started_state,
    }


def execute_issue(
    client: LinearClient,
    issue_ref: str,
    *,
    repo: str | None,
    go: bool,
    force: bool,
    state_update: bool,
    worktree: bool,
) -> dict[str, Any]:
    report = build_execute_report(client, issue_ref, repo=repo)
    blockers = report["relations"]["blockers"]
    actions: list[dict[str, Any]] = []
    if go and blockers and not force:
        report["actions"] = actions
        report["blocked"] = True
        report["error"] = "issue has incomplete blockers; pass --force to override"
        return report

    issue = report["issue"]
    if go and state_update:
        current_type = ((issue.get("state") or {}).get("type") or "").lower()
        started_state = report.get("started_state")
        if current_type not in {"started", "completed", "canceled"} and started_state:
            issue = update_issue_state(client, issue, started_state)
            report["issue"] = issue
            actions.append({
                "type": "state_update",
                "state": started_state.get("name"),
            })

    if go and worktree:
        repo_name = report.get("repo")
        if not repo_name:
            report["actions"] = actions
            report["error"] = "repo could not be inferred; rerun with --repo"
            return report
        path = create_worktree(repo_name, report["worktree_slug"])
        actions.append({"type": "worktree", "path": path, "repo": repo_name})

    report["actions"] = actions
    report["blocked"] = bool(blockers)
    return report


def choose_candidate(
    client: LinearClient,
    priority: int,
    *,
    limit: int,
) -> tuple[list[Candidate], dict[str, Any] | None]:
    candidates: list[Candidate] = []
    for issue in list_candidate_issues(client, priority)[:limit]:
        relations = fetch_issue_relations(client, issue["id"])
        blockers = incomplete_blockers(issue, relations)
        candidates.append(Candidate(issue=issue, blockers=blockers))
    chosen = next((item.issue for item in candidates if not item.blockers), None)
    return candidates, chosen


def render_blockers(blockers: Sequence[dict[str, Any]]) -> str:
    if not blockers:
        return "clear"
    parts = []
    for blocker in blockers:
        state = (blocker.get("state") or {}).get("name") or "?"
        parts.append(f"{blocker.get('identifier')} [{state}] {blocker.get('title')}")
    return "; ".join(parts)


def render_report(report: dict[str, Any], *, go: bool) -> str:
    issue = report["issue"]
    lines = [
        issue_summary(issue),
        f"viewer: {report['viewer'].get('name')} ({report['viewer'].get('organization')})",
        f"repo: {report.get('repo') or 'unknown'}",
        f"relations: {report['relations']['count']} total; blockers: "
        f"{render_blockers(report['relations']['blockers'])}",
    ]
    overlap = report["scope_overlap"]
    if overlap["status"] == "overlap":
        matches = ", ".join(
            f"{m['identifier']}({', '.join(m['overlap'])})"
            for m in overlap["matches"][:5]
        )
        lines.append(f"scope-overlap-check: overlap in {overlap.get('project')}: {matches}")
    elif overlap["status"] == "skipped":
        lines.append(f"scope-overlap-check: skipped ({overlap.get('reason')})")
    else:
        lines.append(f"scope-overlap-check: clean ({overlap.get('project') or 'no project'})")

    if report.get("error"):
        lines.append(f"error: {report['error']}")
    if report.get("actions"):
        for action in report["actions"]:
            if action["type"] == "state_update":
                lines.append(f"action: moved to {action['state']}")
            elif action["type"] == "worktree":
                lines.append(f"action: worktree {action['path']}")
    elif not go:
        command = (
            f"linear-exec execute {issue['identifier']} "
            f"--workspace {infer_workspace(issue['identifier']) or '<workspace>'}"
        )
        if report.get("repo"):
            command += f" --repo {report['repo']}"
        command += " --go"
        lines.append("dry-run: add --go to update Linear and create the worktree")
        lines.append(f"next: {command}")
    return "\n".join(lines)


def cmd_execute(args: argparse.Namespace) -> int:
    workspace = infer_workspace(args.issue, args.workspace)
    client = client_for(workspace)
    report = execute_issue(
        client,
        args.issue,
        repo=args.repo,
        go=args.go,
        force=args.force,
        state_update=not args.no_state_update,
        worktree=not args.no_worktree,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_report(report, go=args.go))
    return 2 if report.get("error") else 0


def cmd_sweep(args: argparse.Namespace) -> int:
    client = client_for(args.workspace)
    candidates, chosen = choose_candidate(
        client,
        args.priority,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps({
            "workspace": args.workspace,
            "priority": args.priority,
            "candidates": [
                {"issue": item.issue, "blockers": item.blockers}
                for item in candidates
            ],
            "chosen": chosen,
        }, indent=2, default=str))
    else:
        print(f"sweep: workspace={args.workspace} priority={args.priority}")
        for item in candidates[:args.limit]:
            marker = "ready" if not item.blockers else "blocked"
            print(
                f"- {marker}: {issue_summary(item.issue)}; "
                f"blockers: {render_blockers(item.blockers)}"
            )
        if not chosen:
            print("next: no unblocked issue found in this window")
            return 1
        print(f"next: {chosen['identifier']} {chosen['title']}")

    if args.go and chosen:
        report = execute_issue(
            client,
            chosen["identifier"],
            repo=args.repo,
            go=True,
            force=args.force,
            state_update=not args.no_state_update,
            worktree=not args.no_worktree,
        )
        if args.json:
            print(json.dumps({"execute": report}, indent=2, default=str))
        else:
            print()
            print(render_report(report, go=True))
        return 2 if report.get("error") else 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linear-exec",
        description="Preflight and start work on Linear issues quickly.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute = subparsers.add_parser("execute", help="Preflight one issue")
    execute.add_argument("issue", help="Issue identifier or UUID")
    execute.add_argument("-w", "--workspace", help="Workspace alias")
    execute.add_argument("--repo", help="Repo name under ~/dev")
    execute.add_argument("--go", action="store_true", help="Apply state/worktree actions")
    execute.add_argument("--force", action="store_true", help="Proceed despite blockers")
    execute.add_argument("--no-state-update", action="store_true", help="Do not move state")
    execute.add_argument("--no-worktree", action="store_true", help="Do not create a worktree")
    execute.add_argument("--json", action="store_true", help="Print JSON")
    execute.set_defaults(func=cmd_execute)

    sweep = subparsers.add_parser("sweep", help="Find the next unblocked issue")
    sweep.add_argument("workspace", help="Workspace alias")
    sweep.add_argument("priority", type=parse_priority, help="Priority like p1 or 1")
    sweep.add_argument("--repo", help="Repo name under ~/dev")
    sweep.add_argument("--limit", type=int, default=5, help="Candidates to print")
    sweep.add_argument("--go", action="store_true", help="Execute the selected issue")
    sweep.add_argument("--force", action="store_true", help="Proceed despite blockers")
    sweep.add_argument("--no-state-update", action="store_true", help="Do not move state")
    sweep.add_argument("--no-worktree", action="store_true", help="Do not create a worktree")
    sweep.add_argument("--json", action="store_true", help="Print JSON")
    sweep.set_defaults(func=cmd_sweep)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and parse_issue_identifier(args[0]):
        args.insert(0, "execute")
    parser = build_parser()
    parsed = parser.parse_args(args)
    try:
        return parsed.func(parsed)
    except Exception as exc:  # noqa: BLE001
        print(f"linear-exec: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
