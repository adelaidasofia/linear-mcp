"""Multi-workspace registry for Linear PATs.

Each workspace is identified by a short alias (`personal`, `work`,
`client-a`, whatever) and backed by a Linear Personal API Key generated
at linear.app/settings/account/security from inside that workspace.

Config is read from `~/.claude/linear-mcp/admin.env` at process start
(and from the surrounding env). Envs are evaluated lazily so adding a
workspace mid-session is picked up on next list_workspaces call after a
server reload.

Format (in admin.env):

    LINEAR_WORKSPACES=personal,work
    LINEAR_PRIMARY_WORKSPACE=personal

    LINEAR_PAT_PERSONAL=lin_api_xxx
    LINEAR_PAT_WORK=lin_api_xxx

    # Optional friendly label per workspace
    LINEAR_LABEL_PERSONAL=Personal
    LINEAR_LABEL_WORK=Work

Convenience: if only one PAT is set and LINEAR_WORKSPACES is unset, the
registry treats it as a single-workspace install with alias `default`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ENV_FILE = Path.home() / ".claude" / "linear-mcp" / "admin.env"


def _load_env_file() -> None:
    """Lightweight .env loader. No python-dotenv dependency."""
    if not ENV_FILE.exists():
        return
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


@dataclass
class Workspace:
    alias: str
    # repr=False keeps the live PAT out of every repr/log/traceback — a failing
    # registry test once printed real tokens. Use .redacted() for debugging.
    token: str = field(repr=False)
    label: str | None = None

    def redacted(self) -> dict:
        return {
            "alias": self.alias,
            "token_prefix": (self.token[:11] + "...") if self.token else "",
            "label": self.label,
        }


@dataclass
class WorkspaceRegistry:
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    primary: str | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "WorkspaceRegistry":
        _load_env_file()
        registry = cls()
        aliases_csv = os.environ.get("LINEAR_WORKSPACES", "").strip()

        # Single-workspace fallback: one bare LINEAR_PAT or LINEAR_API_KEY
        if not aliases_csv:
            single = (
                os.environ.get("LINEAR_PAT", "").strip()
                or os.environ.get("LINEAR_API_KEY", "").strip()
            )
            if single:
                registry.workspaces["default"] = Workspace(
                    alias="default", token=single, label="default"
                )
                registry.primary = "default"
                return registry
            registry.errors.append(
                "LINEAR_WORKSPACES not set. Edit ~/.claude/linear-mcp/admin.env "
                "(see SETUP.md for PAT generation)."
            )
            return registry

        primary = os.environ.get("LINEAR_PRIMARY_WORKSPACE", "").strip().lower() or None
        for alias_raw in aliases_csv.split(","):
            alias = alias_raw.strip().lower()
            if not alias:
                continue
            result = cls._load_one(alias)
            if isinstance(result, Workspace):
                registry.workspaces[alias] = result
            else:
                registry.errors.append(result)
        if primary and primary in registry.workspaces:
            registry.primary = primary
        elif registry.workspaces:
            registry.primary = next(iter(registry.workspaces))
        return registry

    @staticmethod
    def _load_one(alias: str) -> Workspace | str:
        upper = alias.upper().replace("-", "_")
        token = os.environ.get(f"LINEAR_PAT_{upper}", "").strip()
        if not token:
            return (
                f"workspace '{alias}': missing LINEAR_PAT_{upper} "
                "(generate at linear.app/settings/account/security)"
            )
        if not token.startswith("lin_api_"):
            return (
                f"workspace '{alias}': LINEAR_PAT_{upper} must start with 'lin_api_' "
                "(personal API key)"
            )
        label = os.environ.get(f"LINEAR_LABEL_{upper}", "").strip() or alias
        return Workspace(alias=alias, token=token, label=label)

    def get(self, alias: str | None) -> Workspace:
        target = (alias or self.primary or "").strip().lower()
        if not target:
            raise ValueError("no workspace specified and no primary configured")
        if target not in self.workspaces:
            available = ", ".join(self.workspaces) or "(none configured)"
            raise KeyError(f"unknown workspace '{target}'. available: {available}")
        return self.workspaces[target]

    def aliases(self) -> Iterable[str]:
        return list(self.workspaces.keys())


# Loaded once per server process. Restart Claude Code to pick up admin.env edits.
REGISTRY = WorkspaceRegistry.from_env()
