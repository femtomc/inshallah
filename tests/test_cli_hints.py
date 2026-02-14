"""Tests for contextual help, hints, and recovery messaging in inshallah CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from inshallah.cli import _run_parser, cmd_forum, cmd_init, cmd_issues, cmd_resume, cmd_run, cmd_status, main
from inshallah.dag import DagResult
from inshallah.issue_store import IssueStore


def _setup_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    lf = tmp_path / ".inshallah"
    lf.mkdir()
    (lf / "issues.jsonl").touch()
    (lf / "forum.jsonl").touch()


def test_main_help_mentions_guide(capsys) -> None:
    with pytest.raises(SystemExit) as ex:
        main(["--help"])
    assert ex.value.code == 0

    rendered = capsys.readouterr().out
    assert "inshallah guide" in rendered
    assert "Quick Start" in rendered


def test_init_prints_next_steps(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    console = Console(record=True, force_terminal=False)

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_init(console)

    assert rc == 0
    rendered = console.export_text()
    assert "Next Steps" in rendered
    assert "inshallah guide" in rendered
    assert "inshallah run" in rendered


def test_issues_help_has_guide_cross_link(tmp_path: Path) -> None:
    _setup_repo(tmp_path)
    console = Console(record=True, force_terminal=False)

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_issues(["--help"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "inshallah guide --section workflow" in rendered


def test_forum_help_has_guide_cross_link(tmp_path: Path) -> None:
    _setup_repo(tmp_path)
    console = Console(record=True, force_terminal=False)

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_forum(["--help"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "inshallah guide --section workflow" in rendered


def test_issues_unknown_subcommand_includes_recovery(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_issues(["bogus"])

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert "unknown subcommand: bogus" in out["error"]
    assert "inshallah issues --help" in out["error"]
    assert "inshallah guide --section workflow" in out["error"]


def test_forum_limit_error_includes_recovery(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_forum(["read", "issue:abc", "--limit", "0"])

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert "limit must be >= 1" in out["error"]
    assert "inshallah forum read issue:<issue-id> --limit 20" in out["error"]


def test_status_shows_ready_next_steps(tmp_path: Path) -> None:
    _setup_repo(tmp_path)
    store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
    root = store.create("root", tags=["node:agent", "node:root"])
    issue = store.create("leaf", tags=["node:agent"])
    store.add_dep(issue["id"], "parent", root["id"])

    console = Console(record=True, force_terminal=False)
    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_status([], console)

    assert rc == 0
    rendered = console.export_text()
    assert "Next Steps" in rendered
    assert f"inshallah issues get {issue['id']}" in rendered
    assert f"inshallah forum read issue:{issue['id']} --limit 20" in rendered
    assert "inshallah guide --section workflow" in rendered


def test_status_json_has_no_hint_pollution(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    console = Console()

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_status(["--json"], console)

    assert rc == 0
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert payload["repo_root"] == str(tmp_path)
    assert "Next Steps" not in raw
    assert "inshallah guide" not in raw


def test_run_missing_prompt_json_has_recovery(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    args = _run_parser().parse_args(["--json"])

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_run(args, Console())

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert "missing prompt" in out["error"]
    assert "inshallah run" in out["error"]
    assert "inshallah guide --section workflow" in out["error"]


def test_run_json_emits_only_json_payload(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    args = _run_parser().parse_args(["--json", "Ship the feature"])

    with (
        patch("inshallah.cli._find_repo_root", return_value=tmp_path),
        patch("inshallah.cli.DagRunner.run", return_value=DagResult(status="no_executable_leaf", steps=1, error="")),
    ):
        rc = cmd_run(args, Console())

    assert rc == 1
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert payload["status"] == "no_executable_leaf"
    assert "root_id" in payload
    assert "Root Issue" not in raw
    assert "Next Steps" not in raw


def test_resume_json_emits_only_json_payload(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)
    store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
    root = store.create("root", tags=["node:agent", "node:root"])

    with (
        patch("inshallah.cli._find_repo_root", return_value=tmp_path),
        patch("inshallah.cli.DagRunner.run", return_value=DagResult(status="root_final", steps=2, error="")),
    ):
        rc = cmd_resume([root["id"], "--json"], Console())

    assert rc == 0
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert payload["root_id"] == root["id"]
    assert payload["status"] == "root_final"
    assert "Resuming" not in raw
    assert "Next Steps" not in raw


def test_resume_missing_root_json_has_recovery(tmp_path: Path, capsys) -> None:
    _setup_repo(tmp_path)

    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_resume(["missing", "--json"], Console())

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert "Issue not found: missing" in out["error"]
    assert "inshallah status" in out["error"]
    assert "inshallah guide --section workflow" in out["error"]
