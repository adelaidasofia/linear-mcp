"""Meta tools: list_workspaces, healthcheck."""

from __future__ import annotations

from typing import Any

from ..client import LinearClient, LinearError
from ..drafts import STORE
from ..audit import AUDIT_PATH
from ..workspaces import REGISTRY
from ._common import run_tool


def register(mcp) -> None:
    @mcp.tool()
    def list_workspaces() -> dict[str, Any]:
        """List configured Linear workspaces with PAT prefix + primary status.

        Returns a dict with `workspaces` (list of redacted profiles), `primary`
        (alias of the default workspace), and `errors` (config errors found at
        load time). Tokens never appear in the response.
        """
        return run_tool(
            "list_workspaces", {},
            lambda: {
                "workspaces": [REGISTRY.workspaces[a].redacted() for a in REGISTRY.aliases()],
                "primary": REGISTRY.primary,
                "errors": list(REGISTRY.errors),
            },
            lambda r: f"{len(r['workspaces'])} workspaces",
        )

    @mcp.tool()
    def healthcheck() -> dict[str, Any]:
        """Verify PAT validity for each workspace + report draft store + audit log path.

        For each workspace, calls the `viewer` query. Returns user info + the
        organization the PAT is scoped to. A failure means the PAT has been
        revoked or rotated and needs re-generation at
        linear.app/settings/account/security.
        """
        def _run() -> dict[str, Any]:
            results: dict[str, Any] = {}
            for alias in REGISTRY.aliases():
                try:
                    client = LinearClient(REGISTRY.get(alias))
                    viewer = client.viewer()
                    org = viewer.get("organization") or {}
                    results[alias] = {
                        "ok": True,
                        "user_id": viewer.get("id"),
                        "user_name": viewer.get("name") or viewer.get("displayName"),
                        "user_email": viewer.get("email"),
                        "organization": {
                            "id": org.get("id"),
                            "name": org.get("name"),
                            "url_key": org.get("urlKey"),
                        },
                    }
                except LinearError as e:
                    results[alias] = {"ok": False, "error": str(e), "status": e.status}
                except Exception as e:  # noqa: BLE001
                    results[alias] = {"ok": False, "error": str(e)}
            return {
                "workspaces": results,
                "primary": REGISTRY.primary,
                "config_errors": list(REGISTRY.errors),
                "draft_store_size": STORE.size(),
                "audit_log_path": str(AUDIT_PATH),
            }

        return run_tool(
            "healthcheck", {}, _run,
            lambda r: f"{sum(1 for v in r['workspaces'].values() if v.get('ok'))}/{len(r['workspaces'])} ok",
        )
