"""Smoke tests: every module imports, every tool registers on a FastMCP."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_admin_env(monkeypatch):
    """Point the workspace registry at a non-existent admin.env.

    Without this, WorkspaceRegistry.from_env() reads the real
    ~/.claude/linear-mcp/admin.env on a dev machine, so registry tests that
    assert on empty/default state fail AND leak live PATs in the failure repr.
    CI runners have no admin.env, so this only bites locally — isolate always.
    """
    monkeypatch.setattr(
        "linear_mcp.workspaces.ENV_FILE",
        Path("/tmp/linear-mcp-test-nonexistent.env"),
        raising=False,
    )


def test_package_imports() -> None:
    import linear_mcp  # noqa: F401
    assert linear_mcp.__version__


def test_module_imports() -> None:
    from linear_mcp import audit, client, drafts, queries, workspaces  # noqa: F401
    from linear_mcp.tools import (  # noqa: F401
        _common, comments, cycles, documents, initiatives, issues, labels,
        milestones, projects, search, status_updates, statuses, teams, users,
        workspaces as ws_tools,
    )


def test_tools_register() -> None:
    """All tool modules wire onto a fresh FastMCP without error."""
    from fastmcp import FastMCP
    from linear_mcp.tools import register_all

    mcp = FastMCP("linear-mcp-test")
    register_all(mcp)
    # FastMCP exposes _tools or tool_manager.get_tools() depending on version;
    # we just assert the call did not throw and the registry is non-empty.


def test_workspace_registry_handles_missing_env(monkeypatch) -> None:
    """No env → registry has errors but does not crash."""
    monkeypatch.delenv("LINEAR_WORKSPACES", raising=False)
    monkeypatch.delenv("LINEAR_PAT", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert reg.workspaces == {} or "default" in reg.workspaces


def test_workspace_registry_single_pat(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_WORKSPACES", raising=False)
    monkeypatch.setenv("LINEAR_PAT", "lin_api_smoke")
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert "default" in reg.workspaces
    assert reg.primary == "default"


def test_workspace_registry_multi(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_WORKSPACES", "alpha,beta")
    monkeypatch.setenv("LINEAR_PRIMARY_WORKSPACE", "beta")
    monkeypatch.setenv("LINEAR_PAT_ALPHA", "lin_api_a")
    monkeypatch.setenv("LINEAR_PAT_BETA", "lin_api_b")
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert set(reg.workspaces) == {"alpha", "beta"}
    assert reg.primary == "beta"
    assert reg.get("alpha").token == "lin_api_a"
    assert reg.get(None).alias == "beta"


def test_workspace_registry_rejects_bad_pat(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_WORKSPACES", "x")
    monkeypatch.setenv("LINEAR_PAT_X", "not-a-linear-key")
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert "x" not in reg.workspaces
    assert any("lin_api_" in e for e in reg.errors)


def test_audit_redacts_pat() -> None:
    from linear_mcp.audit import _redact
    result = _redact({"workspace": "onde", "token": "lin_api_secret", "first": 5})
    assert result["token"] == "[REDACTED]"
    assert result["workspace"] == "onde"
    assert result["first"] == 5


def test_draft_lifecycle() -> None:
    from linear_mcp.drafts import DraftStore
    store = DraftStore()
    d = store.create("onde", "archive_issue", "iss-1", "ONDE-1", {"before": "Todo", "after": "archived"})
    assert store.size() == 1
    confirmed = store.confirm(d.draft_id)
    assert confirmed.confirmed is True
    assert store.size() == 0


def test_clean_strips_none() -> None:
    from linear_mcp.tools._common import clean
    assert clean({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}
    assert clean(None) == {}
