# Changelog

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
