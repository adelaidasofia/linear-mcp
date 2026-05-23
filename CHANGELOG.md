# Changelog

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
