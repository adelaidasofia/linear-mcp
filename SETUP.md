# Setup

## 1. Generate Personal API Keys

For each Linear workspace you want to access:

1. Sign in to that workspace at <https://linear.app>.
2. Go to <https://linear.app/settings/account/security> (the URL stays the same; you just need to be in the right workspace).
3. Under **Personal API keys**, click **New API key**.
4. Name it (e.g. `mcp-server`), copy the key (`lin_api_...`), and save it.

Repeat for each workspace. There is no cross-workspace token; each workspace issues its own.

## 2. Save the env file

```bash
mkdir -p ~/.claude/linear-mcp
cp admin.env.example ~/.claude/linear-mcp/admin.env
chmod 600 ~/.claude/linear-mcp/admin.env
$EDITOR ~/.claude/linear-mcp/admin.env
```

Set:

```
LINEAR_WORKSPACES=onde,mycelium
LINEAR_PRIMARY_WORKSPACE=onde

LINEAR_PAT_ONDE=lin_api_xxx
LINEAR_PAT_MYCELIUM=lin_api_xxx
```

Aliases are lowercase. Suffixes in env keys match the alias uppercased (and hyphens → underscores).

## 3. Install dependencies

```bash
cd ~/.claude/linear-mcp
pip install -e .
```

Or via pipx for a clean isolated install:

```bash
pipx install adelaidasofia-linear-mcp
```

## 4. Register with Claude Code

```bash
claude mcp add -s user linear-mcp python3 -m linear_mcp.server
```

If you used pipx:

```bash
claude mcp add -s user linear-mcp linear-mcp
```

## 5. Verify

Restart Claude Code, then in any session:

```
healthcheck()
```

Expected: `{ "workspaces": { "onde": { "ok": true, ... }, "mycelium": { "ok": true, ... } } }`.

If a workspace returns `"ok": false, "status": 401`, the PAT was rejected — re-generate and try again.

## 6. Migrating from the official Linear MCP

Remove the OAuth-based instances first:

```bash
claude mcp remove linear -s user
claude mcp remove mycelium-linear -s user
```

Then add `linear-mcp` as above. Restart Claude Code.

## Troubleshooting

- **"LINEAR_WORKSPACES not set"** — admin.env not found or not loaded. Confirm path is `~/.claude/linear-mcp/admin.env` and aliases are comma-separated with no spaces.
- **"PAT must start with `lin_api_`"** — copied the wrong value from Linear's UI. The key starts with `lin_api_`.
- **`healthcheck` returns 401** — PAT revoked or rotated. Re-generate at `linear.app/settings/account/security`.
- **`healthcheck` returns 429** — rate limit (1500 req/hr per token). Wait `Retry-After` seconds.

## Audit log

Every tool call appends one JSONL line to `~/.claude/linear-mcp/audit.log`. Tokens are stripped. Tail it:

```bash
tail -f ~/.claude/linear-mcp/audit.log | jq .
```
