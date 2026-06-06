# linear-mcp

<!-- mcp-name: io.github.adelaidasofia/linear-mcp -->

Multi-workspace Linear MCP server with Personal API Key auth. Drop-in replacement for the official OAuth-only Linear MCP at `mcp.linear.app/mcp`.

**Why this exists.** The official Linear MCP is OAuth-only and single-workspace per instance. PAT auth plus persistent token storage plus multi-workspace routing kills three failure modes:

1. The OAuth flow is brittle across MCP client session boundaries — auth state expires when a session resumes mid-flow.
2. The localhost callback fails in some setups, forcing fragile paste-back flows.
3. One MCP instance per workspace doubles config + OAuth dances.

This server replaces both with one entry. One install, N workspaces, never an OAuth dance again.

## Install

### From PyPI

```bash
pipx install adelaidasofia-linear-mcp
```

### From source

```bash
git clone https://github.com/adelaidasofia/linear-mcp ~/.claude/linear-mcp
cd ~/.claude/linear-mcp
pip install -e .
```

### Claude Desktop one-click

Download the latest `.mcpb` from [Releases](https://github.com/adelaidasofia/linear-mcp/releases) and double-click.

## Configure

1. Generate one **Personal API Key per workspace** at <https://linear.app/settings/account/security>. You must be logged into each workspace separately while generating the key for that workspace.

2. Create `~/.claude/linear-mcp/admin.env` (chmod 600):

```bash
LINEAR_WORKSPACES=personal,work
LINEAR_PRIMARY_WORKSPACE=personal

LINEAR_PAT_PERSONAL=lin_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
LINEAR_PAT_WORK=lin_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

LINEAR_LABEL_PERSONAL=Personal
LINEAR_LABEL_WORK=Work
```

Aliases are arbitrary — name them whatever helps you route (`acme,beta`, `team1,team2`, `home,client`).

```bash
chmod 600 ~/.claude/linear-mcp/admin.env
```

3. Register in Claude Code (user scope, so it loads in every project):

```bash
claude mcp add -s user linear-mcp python3 -m linear_mcp.server
```

Or, with `pipx` install:

```bash
claude mcp add -s user linear-mcp linear-mcp
```

4. Restart Claude Code. `healthcheck` should return `ok: true` per workspace.

## Substrate-layer enforcement (v0.3)

Three server-side checks that protect issue quality without depending on any markdown rule file or client-side memory. Apply only to WRITE paths; reads stay unconstrained.

| Layer | What it does | Bypass env var |
|---|---|---|
| `[source:]` first-line check | `save_issue` / `save_project` reject CREATE calls whose `description` (or project `content`) does not start with `[source: <canonical-key>]`. UPDATE calls (`id` passed) skip the check so legacy backfills remain unblocked. | `LINEAR_MCP_SKIP_SOURCE_CHECK=1` |
| Idempotency check | Before any CREATE, the server runs `searchIssues` / `searchProjects` for `[source: <key>]` and refuses to create a duplicate. The error names the existing identifier + UUID so the caller can update in place. | `LINEAR_MCP_SKIP_IDEMPOTENCY=1` |
| `auth_phrase` on `bulk_save_issues` | `bulk_save_issues` now requires `auth_phrase` ∈ {`"go"`, `"yes do it"`, `"confirmed"`, `"execute"`, `"go cancel"`, `"go update"`} (case-insensitive). Mass-modification surface stays explicit. | (no bypass — surface the phrase to the operator) |

Canonical-key examples:

- `[source: 🍄 Mycelium AI/📝 Meeting Notes/2026-05-22 - sync.md]`
- `[source: ⚙️ Meta/Decisions/2026-05-23-merger-public-comms.md]`
- `[source: linear-kickoff:sweep-myc-p1]`
- `[source: ~/.claude/linear-mcp/BUILD_PROMPT_V03.md]`

## Fast issue execution

`linear-exec` is the short path for starting real work from a Linear issue.
It resolves the issue, checks blocking relations, scans same-project siblings
for obvious scope overlap, infers the repo when possible, and can create the
standard `claude-dev-worktree` branch.

Dry-run a specific issue:

```bash
linear-exec execute MYC-150 --workspace mycelium
```

Start the work after reviewing the preflight:

```bash
linear-exec execute MYC-150 --workspace mycelium --repo memory-runtime-pro --go
```

Find the next unblocked P1 issue in a workspace:

```bash
linear-exec sweep mycelium p1
linear-exec sweep mycelium p1 --go --repo memory-runtime-pro
```

The command refuses to proceed when an upstream `blocks` relation is still
incomplete unless `--force` is passed. `--no-state-update` and `--no-worktree`
let agents use only the parts of the preflight they need.

## Tool surface (v0.3 — 57 tools + 3 prompts)

Every tool takes an optional `workspace` parameter (the alias from `LINEAR_WORKSPACES`). Omit it to use `LINEAR_PRIMARY_WORKSPACE`.

### Meta

| Tool | Purpose |
|---|---|
| `list_workspaces` | Show configured workspaces and primary |
| `healthcheck` | Verify each PAT + surface remaining rate-limit budget |

### Core entities

| Tool | Purpose |
|---|---|
| `list_teams` / `get_team` | Teams (with inline workflow states) |
| `list_users` / `get_user` | Users (`me` resolves to PAT owner) |
| `list_projects` / `get_project` / `save_project` | Projects (v0.3: `save_project` enforces `[source:]` on `content` + idempotency on CREATE) |
| `list_initiatives` / `get_initiative` / `save_initiative` | Initiatives |
| `list_issues` / `get_issue` / `save_issue` / `bulk_save_issues` | Issues (id or `ONDE-123`; bulk uses `issueBatchUpdate`; v0.3: `save_issue` enforces `[source:]` + idempotency on CREATE; `bulk_save_issues` requires `auth_phrase`) |
| `list_cycles` | Cycles |
| `list_milestones` / `get_milestone` / `save_milestone` | Project milestones |
| `list_issue_statuses` / `get_issue_status` | Workflow states |
| `list_issue_labels` / `create_issue_label` | Labels |
| `list_comments` / `save_comment` | Comments |
| `list_documents` / `get_document` / `save_document` | Documents |
| `save_status_update` | Post a project status update |

### Webhooks (v0.2)

| Tool | Purpose |
|---|---|
| `list_webhooks` / `get_webhook` | Inspect subscriptions |
| `create_webhook` / `update_webhook` | Manage subscriptions |
| `delete_webhook` | Destructive — draft+confirm |

### Notifications / inbox (v0.2)

| Tool | Purpose |
|---|---|
| `list_notifications` / `get_notification` | Inbox read |
| `notifications_unread_count` | Top-of-mind counter |
| `mark_notification_read` / `mark_all_notifications_read` | Triage |
| `archive_notification` | Sweep |

### Attachments (v0.2)

| Tool | Purpose |
|---|---|
| `list_attachments` / `get_attachment` | Per-issue reads |
| `attachments_for_url` | Reverse lookup: which issues link to this URL? |
| `link_url_to_issue` | Attach any URL to an issue |
| `delete_attachment` | Destructive — draft+confirm |

### Issue relations (v0.2)

| Tool | Purpose |
|---|---|
| `list_issue_relations` | The blocks/duplicate/related graph |
| `create_issue_relation` / `delete_issue_relation` | Manage the graph |

### Agent sessions (v0.2)

| Tool | Purpose |
|---|---|
| `list_agent_sessions` / `get_agent_session` | Linear's first-class agent surface |
| `create_agent_session_on_issue` / `create_agent_session_on_comment` | Spawn |

### Search (v0.2 — replaces v0.1's broken `search_documentation`)

| Tool | Purpose |
|---|---|
| `search_issues` / `search_documents` / `search_projects` | Full-text per entity type |
| `semantic_search` | Workspace-wide semantic across all entities |

### MCP prompts (v0.2)

Available as slash commands in MCP clients that surface prompts:

- `/triage-issue` — full triage pass: classify, label, prioritize, assign, link duplicates
- `/project-status` — draft a weekly status update from current Linear state
- `/inbox-sweep` — sweep today's notifications, propose actions, archive what's handled

## Multi-workspace usage

Switch workspaces inline:

```
list_teams(workspace="work")
save_issue(workspace="personal", title="Ship", team_id="...")
```

Without `workspace`, the primary is used.

## Auth

Linear PATs use header `Authorization: <key>` (no `Bearer` prefix). Each PAT is scoped to one workspace and grants access only to data the owning user can see. There is no shared org token.

Rate limit: 2500 requests/hour per token (verified against live API 2026-05-23). The server passes Linear's `Retry-After` header through on 429 and surfaces remaining budget via `healthcheck`.

## Safety

Read tools and routine writes (create/update issues, comments, labels, status updates) pass through. Destructive ops (`delete_webhook`, `delete_attachment`) use the **draft+confirm** pattern: the first call stages the change and returns a `draft_id` + preview of what will happen; the second call (with `confirm_draft_id`) commits. Drafts expire after 1 hour (override with `LINEAR_MCP_DRAFT_TTL_SECONDS`).

Every tool call appends one JSONL line to `~/.claude/linear-mcp/audit.log` (override with `LINEAR_MCP_AUDIT_LOG_PATH`, disable with `LINEAR_MCP_AUDIT_LOG=false`). Tokens are stripped from audit records.

`healthcheck` surfaces each PAT's remaining rate-limit budget (`X-RateLimit-Requests-Remaining` + `X-Complexity-Remaining`) per workspace, so agents can self-throttle without making a separate observability call.

## Related MCPs

- [adelaidasofia/slack-mcp](https://github.com/adelaidasofia/slack-mcp) — multi-workspace Slack with draft+confirm
- [adelaidasofia/whatsapp-mcp](https://github.com/adelaidasofia/whatsapp-mcp) — WhatsApp via whatsmeow + vault export
- [adelaidasofia/imessage-mcp](https://github.com/adelaidasofia/imessage-mcp) — iMessage chat.db + vault export
- [adelaidasofia/github-mcp](https://github.com/adelaidasofia/github-mcp) — GitHub PR/issue/release

## License

MIT.

---

Built by Adelaida Diaz-Roa. Full install or team version at [diazroa.com](https://diazroa.com).
