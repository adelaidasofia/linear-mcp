"""Bare smoke test runner — no pytest dependency.

Run with: python3 tests/smoke.py
Exits 0 on success, 1 on any failure with the failing test named.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label: str) -> None:
    if not cond:
        raise AssertionError(label)


def clear_linear_env() -> None:
    for k in list(os.environ):
        if k.startswith("LINEAR_"):
            del os.environ[k]


def isolate_registry_from_admin_env():
    """Point the workspace registry's ENV_FILE at a path that does not exist.

    Returns the (module, original_path) so the caller can restore it.
    Without this, every from_env() call re-loads ~/.claude/linear-mcp/admin.env
    which leaks LINEAR_* keys back into os.environ between tests.
    """
    from pathlib import Path
    from linear_mcp import workspaces as ws_mod
    original = ws_mod.ENV_FILE
    ws_mod.ENV_FILE = Path("/tmp/linear-mcp-smoke-nonexistent.env")
    return ws_mod, original


def test_package_imports() -> None:
    import linear_mcp
    assert_true(bool(linear_mcp.__version__), "version is set")


def test_module_imports() -> None:
    from linear_mcp import audit, client, drafts, prompts, queries, workspaces  # noqa: F401
    from linear_mcp.tools import (  # noqa: F401
        _common, comments, cycles, documents, initiatives, issues, labels,
        milestones, projects, search, status_updates, statuses, teams, users,
        workspaces as ws_tools,
        # v0.2 additions
        webhooks, notifications, attachments, relations, agent_sessions,
    )


def test_tools_register() -> None:
    from fastmcp import FastMCP
    from linear_mcp.tools import register_all
    from linear_mcp import prompts
    mcp = FastMCP("linear-mcp-smoke")
    register_all(mcp)
    prompts.register(mcp)


def test_tool_count_meets_v02_bar() -> None:
    """v0.2 ships >=50 tools (v0.1 baseline 30 + v0.2 webhooks/notifications/attachments/relations/agent-sessions/search/bulk)."""
    import asyncio
    from fastmcp import FastMCP
    from linear_mcp.tools import register_all
    mcp = FastMCP("linear-mcp-count")
    register_all(mcp)
    tools = asyncio.run(mcp.list_tools())
    assert_true(len(tools) >= 50, f"v0.2 bar: expected >=50 tools, got {len(tools)}")


def test_prompts_register() -> None:
    """The three v0.2 MCP prompts (triage-issue, project-status, inbox-sweep) all register."""
    import asyncio
    from fastmcp import FastMCP
    from linear_mcp import prompts
    mcp = FastMCP("linear-mcp-prompts")
    prompts.register(mcp)
    prompt_list = asyncio.run(mcp.list_prompts())
    names = {p.name for p in prompt_list}
    expected = {"triage-issue", "project-status", "inbox-sweep"}
    missing = expected - names
    assert_true(not missing, f"prompts: missing {missing}, got {names}")


def test_paginate_all_helper_signature() -> None:
    """paginate_all is callable and respects max_pages bound."""
    from linear_mcp.tools._common import paginate_all, MAX_AUTO_PAGES
    assert_true(callable(paginate_all), "paginate_all callable")
    assert_true(MAX_AUTO_PAGES == 20, "default max_pages cap is 20")


def test_client_captures_rate_limit_attribute() -> None:
    """LinearClient instances have a last_rate_limit dict attr."""
    from linear_mcp.client import LinearClient
    from linear_mcp.workspaces import Workspace
    c = LinearClient(Workspace(alias="smoke", token="lin_api_smoke"))
    assert_eq(c.last_rate_limit, {}, "client: last_rate_limit init")


def test_search_module_no_documentation_tool() -> None:
    """v0.2 must NOT expose the broken v0.1 search_documentation tool."""
    import asyncio
    from fastmcp import FastMCP
    from linear_mcp.tools import search
    mcp = FastMCP("linear-mcp-search")
    search.register(mcp)
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert_true("search_documentation" not in names,
                f"v0.2 must drop fake search_documentation; got {names}")
    for expected in ("search_issues", "search_documents", "search_projects", "semantic_search"):
        assert_true(expected in names, f"search: missing {expected} in {names}")


def test_registry_no_env() -> None:
    clear_linear_env()
    ws_mod, original = isolate_registry_from_admin_env()
    try:
        reg = ws_mod.WorkspaceRegistry.from_env()
        assert_true(reg.workspaces == {}, "no-env: registry must be empty")
        assert_true(any("LINEAR_WORKSPACES not set" in e for e in reg.errors),
                    "no-env: error mentions LINEAR_WORKSPACES")
    finally:
        ws_mod.ENV_FILE = original


def test_registry_single_pat() -> None:
    clear_linear_env()
    ws_mod, original = isolate_registry_from_admin_env()
    try:
        os.environ["LINEAR_PAT"] = "lin_api_smoke"
        reg = ws_mod.WorkspaceRegistry.from_env()
        assert_true("default" in reg.workspaces, "single PAT: default workspace exists")
        assert_eq(reg.primary, "default", "single PAT: primary")
    finally:
        ws_mod.ENV_FILE = original


def test_registry_multi() -> None:
    clear_linear_env()
    ws_mod, original = isolate_registry_from_admin_env()
    try:
        os.environ["LINEAR_WORKSPACES"] = "alpha,beta"
        os.environ["LINEAR_PRIMARY_WORKSPACE"] = "beta"
        os.environ["LINEAR_PAT_ALPHA"] = "lin_api_a"
        os.environ["LINEAR_PAT_BETA"] = "lin_api_b"
        reg = ws_mod.WorkspaceRegistry.from_env()
        assert_eq(set(reg.workspaces), {"alpha", "beta"}, "multi: aliases")
        assert_eq(reg.primary, "beta", "multi: primary")
        assert_eq(reg.get("alpha").token, "lin_api_a", "multi: get alpha")
        assert_eq(reg.get(None).alias, "beta", "multi: get default")
    finally:
        ws_mod.ENV_FILE = original


def test_registry_rejects_bad_pat() -> None:
    clear_linear_env()
    ws_mod, original = isolate_registry_from_admin_env()
    try:
        os.environ["LINEAR_WORKSPACES"] = "x"
        os.environ["LINEAR_PAT_X"] = "not-a-linear-key"
        reg = ws_mod.WorkspaceRegistry.from_env()
        assert_true("x" not in reg.workspaces, "bad-prefix: rejected")
        assert_true(any("lin_api_" in e for e in reg.errors), "bad-prefix: error mentions lin_api_")
    finally:
        ws_mod.ENV_FILE = original


def test_audit_redacts_pat() -> None:
    from linear_mcp.audit import _redact
    r = _redact({"workspace": "onde", "token": "lin_api_secret", "first": 5})
    assert_eq(r["token"], "[REDACTED]", "audit: token redacted")
    assert_eq(r["workspace"], "onde", "audit: workspace kept")
    assert_eq(r["first"], 5, "audit: first kept")


def test_draft_lifecycle() -> None:
    from linear_mcp.drafts import DraftStore
    store = DraftStore()
    d = store.create("onde", "archive_issue", "iss-1", "ONDE-1",
                     {"before": "Todo", "after": "archived"})
    assert_eq(store.size(), 1, "draft: size after create")
    confirmed = store.confirm(d.draft_id)
    assert_true(confirmed.confirmed, "draft: confirmed flag set")
    assert_eq(store.size(), 0, "draft: size after confirm")


def test_clean_strips_none() -> None:
    from linear_mcp.tools._common import clean
    assert_eq(clean({"a": 1, "b": None, "c": "x"}), {"a": 1, "c": "x"}, "clean: drops None")
    assert_eq(clean(None), {}, "clean: None input → {}")


def test_queries_compile() -> None:
    """Every GraphQL string compiles to non-empty without f-string surprises."""
    from linear_mcp import queries
    for name in dir(queries):
        if name.startswith("_") or name.islower():
            continue
        val = getattr(queries, name)
        if isinstance(val, str):
            assert_true(len(val.strip()) > 20, f"queries.{name}: non-trivial body")
            # Catch unresolved fragments
            assert_true("{{" not in val and "}}" not in val,
                        f"queries.{name}: no unresolved f-string braces")


TESTS = [
    test_package_imports,
    test_module_imports,
    test_tools_register,
    test_tool_count_meets_v02_bar,
    test_prompts_register,
    test_paginate_all_helper_signature,
    test_client_captures_rate_limit_attribute,
    test_search_module_no_documentation_tool,
    test_registry_no_env,
    test_registry_single_pat,
    test_registry_multi,
    test_registry_rejects_bad_pat,
    test_audit_redacts_pat,
    test_draft_lifecycle,
    test_clean_strips_none,
    test_queries_compile,
]


def main() -> int:
    failed = []
    for test in TESTS:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as e:  # noqa: BLE001
            failed.append((test.__name__, e))
            print(f"  FAIL  {test.__name__}: {e}")
            traceback.print_exc()
    print()
    print(f"{len(TESTS) - len(failed)}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
