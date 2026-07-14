"""Focused tests for the standalone Linear CLI command wiring."""

from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest


@pytest.fixture()
def cli_module():
    script = Path(__file__).parents[1] / "scripts" / "linear-cli.py"
    spec = importlib.util.spec_from_file_location("linear_cli", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[tuple[str, dict | None]] = []
        self.last_rate_limit = None

    def request(self, query: str, variables: dict | None = None) -> dict:
        self.calls.append((query, variables))
        return self.responses[query]

    def viewer(self) -> dict:
        return {"id": "viewer-id"}


def test_search_uses_graphql_term_parameter(cli_module, monkeypatch, capsys) -> None:
    client = FakeClient({cli_module.queries.SEARCH_ISSUES: {"searchIssues": {"nodes": []}}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_search(Namespace(workspace=None, query="native app", limit=12, json=True, verbose=False))

    assert client.calls == [
        (cli_module.queries.SEARCH_ISSUES, {"term": "native app", "first": 12})
    ]
    assert capsys.readouterr().out == "[]\n"


def test_list_wraps_filters_in_issue_filter(cli_module, monkeypatch) -> None:
    client = FakeClient({cli_module.queries.LIST_ISSUES: {"issues": {"nodes": []}}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_list(
        Namespace(
            workspace=None,
            state="In Progress",
            assignee="me",
            team="team-id",
            project="project-id",
            query="swiftui",
            limit=15,
            json=True,
            verbose=False,
        )
    )

    assert client.calls == [
        (
            cli_module.queries.LIST_ISSUES,
            {
                "first": 15,
                "filter": {
                    "state": {"name": {"eqIgnoreCase": "In Progress"}},
                    "assignee": {"isMe": {"eq": True}},
                    "team": {"id": {"eq": "team-id"}},
                    "project": {"id": {"eq": "project-id"}},
                    "searchableContent": {"contains": "swiftui"},
                },
            },
        )
    ]


def test_get_uses_variables_not_string_interpolation(cli_module, monkeypatch) -> None:
    issue = {"id": "issue-id", "identifier": "MYC-1", "title": "Safe", "state": {}, "assignee": {}}
    client = FakeClient({cli_module.queries.GET_ISSUE: {"issue": issue}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_get(
        Namespace(workspace=None, issue_id='MYC-1") { viewer { id } } #', json=True, verbose=False)
    )

    assert client.calls == [
        (cli_module.queries.GET_ISSUE, {"id": 'MYC-1") { viewer { id } } #'})
    ]


def test_get_resolves_human_identifier(cli_module, monkeypatch) -> None:
    issue = {"id": "issue-id", "identifier": "MYC-116", "title": "Native", "state": {}, "assignee": {}}
    client = FakeClient({cli_module.queries.GET_ISSUE_BY_IDENTIFIER: {"issues": {"nodes": [issue]}}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_get(Namespace(workspace=None, issue_id="MYC-116", json=True, verbose=False))

    assert client.calls == [
        (cli_module.queries.GET_ISSUE_BY_IDENTIFIER, {"team": "MYC", "number": 116.0})
    ]


def test_create_applies_source_checks_and_optional_fields(cli_module, monkeypatch, capsys) -> None:
    issue = {
        "id": "issue-id",
        "identifier": "MYC-2",
        "title": "Native client",
        "state": None,
        "assignee": None,
    }
    client = FakeClient({cli_module.queries.ISSUE_CREATE: {"issueCreate": {"issue": issue}}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))
    source_calls: list[tuple] = []
    duplicate_calls: list[tuple] = []
    monkeypatch.setattr(
        cli_module,
        "assert_source_first_line",
        lambda description, *, tool, field: source_calls.append((description, tool, field)) or "native-foundation",
    )
    monkeypatch.setattr(
        cli_module,
        "assert_no_duplicate_source",
        lambda *args, **kwargs: duplicate_calls.append((args, kwargs)),
    )

    cli_module.cmd_create(
        Namespace(
            workspace=None,
            title="Native client",
            team="team-id",
            description="[source: test:native]\n\nBody",
            parent="parent-id",
            priority=3,
            label=["ios-label", "platform-label"],
            json=False,
            verbose=False,
        )
    )

    assert source_calls == [
        ("[source: test:native]\n\nBody", "linear-cli create", "description")
    ]
    assert len(duplicate_calls) == 1
    assert client.calls == [
        (
            cli_module.queries.ISSUE_CREATE,
            {
                "input": {
                    "title": "Native client",
                    "description": "[source: test:native]\n\nBody",
                    "teamId": "team-id",
                    "parentId": "parent-id",
                    "priority": 3,
                    "labelIds": ["ios-label", "platform-label"],
                }
            },
        )
    ]
    assert capsys.readouterr().out == "Created: MYC-2: Native client\n"


def test_update_resolves_named_state_from_workflow_states(cli_module, monkeypatch, capsys) -> None:
    client = FakeClient(
        {
            cli_module.queries.LIST_ISSUE_STATUSES: {
                "workflowStates": {
                    "nodes": [
                        {"id": "todo-id", "name": "Todo"},
                        {"id": "done-id", "name": "Done"},
                    ]
                }
            },
            cli_module.queries.ISSUE_UPDATE: {
                "issueUpdate": {
                    "issue": {
                        "identifier": "MYC-3",
                        "state": {"name": "Done"},
                        "assignee": None,
                    }
                }
            },
        }
    )
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_update(
        Namespace(
            workspace=None,
            issue_id="MYC-3",
            state="done",
            assignee=None,
            priority=None,
            json=False,
            verbose=False,
        )
    )

    assert client.calls == [
        (cli_module.queries.LIST_ISSUE_STATUSES, None),
        (
            cli_module.queries.ISSUE_UPDATE,
            {"id": "MYC-3", "input": {"stateId": "done-id"}},
        ),
    ]
    assert capsys.readouterr().out == "Updated: MYC-3 → Done\n"


def test_update_keeps_zero_priority(cli_module, monkeypatch) -> None:
    client = FakeClient({cli_module.queries.ISSUE_UPDATE: {"issueUpdate": {"issue": {"identifier": "MYC-3", "state": {}}}}})
    monkeypatch.setattr(cli_module, "get_client", lambda workspace: (client, "test"))

    cli_module.cmd_update(
        Namespace(workspace=None, issue_id="issue-id", state=None, assignee=None, priority=0, json=True, verbose=False)
    )

    assert client.calls == [
        (cli_module.queries.ISSUE_UPDATE, {"id": "issue-id", "input": {"priority": 0}})
    ]
