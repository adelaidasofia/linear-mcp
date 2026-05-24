# Changelog

## [0.3.0] - 2026-05-23

Substrate-layer enforcement. v0.2.0 ships the surface; the issue-quality conventions (`[source:]` first-line, idempotency, explicit auth on bulk ops) lived only in advisory markdown rules and broke silently whenever a session forgot the rule files. v0.3 moves the floor into the MCP server — every future caller, regardless of which rules it loaded, gets the same hard guarantees.

### Added (enforcement, not new tools — surface stays at 57 tools + 3 prompts)

- **`[source:]` first-line check** on `save_issue` and `save_project` CREATE paths. Description (or `content` on projects) must start with `[source: <canonical-key>]`. Bypass: `LINEAR_MCP_SKIP_SOURCE_CHECK=1` (legacy backfills only). UPDATE calls (`id` passed) skip the check — backfilling legacy issues stays unblocked.
- **Idempotency check** via `searchIssues` / `searchProjects` on CREATE paths. If an entity with the same `[source:]` key already exists, the create is rejected and the existing identifier + UUID is surfaced for in-place update. Bypass: `LINEAR_MCP_SKIP_IDEMPOTENCY=1` to force-create a duplicate.
- **`auth_phrase` required parameter on `bulk_save_issues`**. Must be one of: `"go"`, `"yes do it"`, `"confirmed"`, `"execute"`, `"go cancel"`, `"go update"` (case-insensitive, whitespace-trimmed). Without it, the call is rejected before any field is sent to Linear. Protects against accidental mass-modification of pre-existing shared workspace data.

### Improved

- **Smoke tests** — 16 → 26 cases. Every layer has positive + negative + bypass coverage; the new `bulk_save_issues` signature is asserted at the MCP tool-schema level so any future refactor that drops `auth_phrase` fails CI.
- **User-Agent** bumped to `linear-mcp/0.3.0`.

### Why this version

`v0.2.0` shipped drop-in compatibility with the official Linear MCP. The same 2026-05-23 session that built it also wrote `linear-session-kickoff.md` trying to teach future Claude Code sessions to use Linear correctly. That rule depended on the session loading the rule file and remembering mid-flow — it advised, it didn't enforce. v0.3 collapses the trust gap by pushing the rule into the substrate.

### Compatibility

Drop-in for v0.2.0 callers on READ tools and UPDATE paths. NEW CREATE calls that lacked a `[source:]` first line in v0.2 will now fail until either the description is updated or the bypass env var is set. `bulk_save_issues` callers MUST add `auth_phrase` — there is no bypass.

## [0.2.0] - 2026-05-23

Closing the gap to best-of-breed after a landscape audit found tacticlaunch/mcp-linear and dvcrn/mcp-server-linear already shipped features v0.1.0 didn't have.

### Added (5 new tool modules, 27 new tools, 3 MCP prompts)

- **Webhooks** (`list/get/create/update/delete_webhook`) — full subscription management for Issue / Comment / Project / Cycle / IssueLabel / ProjectUpdate / Reaction / User events. `delete_webhook` uses the draft+confirm pattern.
- **Notifications / inbox** (`list/get_notification`, `notifications_unread_count`, `mark_notification_read`, `mark_all_notifications_read`, `archive_notification`) — full inbox triage surface.
- **Attachments** (`list_attachments`, `attachments_for_url`, `get_attachment`, `link_url_to_issue`, `delete_attachment`) — URL-linking flow + reverse lookup. `delete_attachment` uses draft+confirm.
- **Issue relations** (`list_issue_relations`, `create_issue_relation`, `delete_issue_relation`) — blocks / duplicate / related graph between issues.
- **Agent sessions** (`list/get_agent_session`, `create_agent_session_on_issue`, `create_agent_session_on_comment`) — Linear's first-class agent surface.
- **Bulk** (`bulk_save_issues`) — `issueBatchUpdate` for one-shot multi-issue field changes.
- **Search** — four real tools (`search_issues`, `search_documents`, `search_projects`, `semantic_search`) replacing v0.1's `search_documentation` (which hit a non-existent endpoint — **REMOVED**).
- **MCP prompts** (`/triage-issue`, `/project-status`, `/inbox-sweep`) — canned workflows the MCP client surfaces as slash commands.

### Improved

- **Rate-limit observability** — every response captures `X-RateLimit-Requests-{Limit,Remaining,Reset}` and `X-Complexity-{Limit,Remaining,Reset}` headers; `healthcheck` surfaces remaining budget per workspace.
- **Auto-pagination helper** (`tools/_common.paginate_all`) — walks every page of a list query up to a configurable `max_pages` cap (default 20).
- **CI** — `.github/workflows/ci.yml` runs `pytest tests/ -v` + bare smoke runner + server-imports check on Python 3.11 / 3.12 / 3.13.
- **GraphQL surface verified** — every query and mutation in `queries.py` was confirmed against `api.linear.app/graphql` schema introspection 2026-05-23. The fake v0.1 `searchDocumentation` query was the only field that did not exist; removed.

### Removed

- `search_documentation` tool — hit a non-existent endpoint (`linear.app/api/docs/search` returns 404). Replaced by four real workspace-search tools.

### Surface count

v0.1.0 shipped 30 tools. v0.2.0 ships **57 tools + 3 MCP prompts**.

## [0.1.0] - 2026-05-23

Initial release.

- Multi-workspace registry from a single `admin.env` (no OAuth flow anywhere)
- Per-workspace Personal API Key auth (`Authorization: <key>`)
- 30 tools across teams / users / projects / initiatives / issues / cycles / milestones / statuses / labels / comments / documents / status updates / docs search
- `list_workspaces` + `healthcheck` for visibility into the registry
- JSONL audit log with token redaction
- Draft+confirm scaffolding for destructive ops (exposed in 0.2.0)
- `me` resolves to PAT owner for `assignee_id` and `get_user`
- Human-identifier resolution for `get_issue` (e.g. `ONDE-123`)
- MCPB bundle for Claude Desktop one-click install
- Submitted to registry.modelcontextprotocol.io as `io.github.adelaidasofia/linear-mcp`
