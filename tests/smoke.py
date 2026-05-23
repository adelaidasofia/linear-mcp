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


def test_package_imports() -> None:
    import linear_mcp
    assert_true(bool(linear_mcp.__version__), "version is set")


def test_module_imports() -> None:
    from linear_mcp import audit, client, drafts, queries, workspaces  # noqa: F401
    from linear_mcp.tools import (  # noqa: F401
        _common, comments, cycles, documents, initiatives, issues, labels,
        milestones, projects, search, status_updates, statuses, teams, users,
        workspaces as ws_tools,
    )


def test_tools_register() -> None:
    from fastmcp import FastMCP
    from linear_mcp.tools import register_all
    mcp = FastMCP("linear-mcp-smoke")
    register_all(mcp)


def test_registry_no_env() -> None:
    clear_linear_env()
    # Force re-load by re-importing the workspaces module
    import importlib
    from linear_mcp import workspaces as ws
    importlib.reload(ws)
    reg = ws.WorkspaceRegistry.from_env()
    assert_true(reg.workspaces == {} or "default" in reg.workspaces,
                "no-env: either empty or has stray single-PAT default")


def test_registry_single_pat() -> None:
    clear_linear_env()
    os.environ["LINEAR_PAT"] = "lin_api_smoke"
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert_true("default" in reg.workspaces, "single PAT: default workspace exists")
    assert_eq(reg.primary, "default", "single PAT: primary")


def test_registry_multi() -> None:
    clear_linear_env()
    os.environ["LINEAR_WORKSPACES"] = "alpha,beta"
    os.environ["LINEAR_PRIMARY_WORKSPACE"] = "beta"
    os.environ["LINEAR_PAT_ALPHA"] = "lin_api_a"
    os.environ["LINEAR_PAT_BETA"] = "lin_api_b"
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert_eq(set(reg.workspaces), {"alpha", "beta"}, "multi: aliases")
    assert_eq(reg.primary, "beta", "multi: primary")
    assert_eq(reg.get("alpha").token, "lin_api_a", "multi: get alpha")
    assert_eq(reg.get(None).alias, "beta", "multi: get default")


def test_registry_rejects_bad_pat() -> None:
    clear_linear_env()
    os.environ["LINEAR_WORKSPACES"] = "x"
    os.environ["LINEAR_PAT_X"] = "not-a-linear-key"
    from linear_mcp.workspaces import WorkspaceRegistry
    reg = WorkspaceRegistry.from_env()
    assert_true("x" not in reg.workspaces, "bad-prefix: rejected")
    assert_true(any("lin_api_" in e for e in reg.errors), "bad-prefix: error mentions lin_api_")


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
