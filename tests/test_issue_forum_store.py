from __future__ import annotations

import json
from pathlib import Path

from loopfarm import cli
from loopfarm.forum import Forum
from loopfarm.issue import Issue


def test_forum_round_trip_json_message(tmp_path: Path) -> None:
    forum = Forum.from_workdir(tmp_path)

    forum.post_json("loopfarm:test", {"status": "ok", "count": 1})
    rows = forum.read_json("loopfarm:test", limit=1)

    assert len(rows) == 1
    payload = json.loads(rows[0]["body"])
    assert payload["status"] == "ok"
    assert payload["count"] == 1


def test_issue_ready_prefers_leaf_and_unblocked(tmp_path: Path) -> None:
    issue = Issue.from_workdir(tmp_path)

    parent = issue.create("Parent epic", priority=2)
    child = issue.create("Leaf task", priority=1)
    blocker = issue.create("Blocking task", priority=1)
    blocked = issue.create("Blocked task", priority=1)

    issue.add_dep(parent["id"], "parent", child["id"])
    issue.add_dep(blocker["id"], "blocks", blocked["id"])

    ready_ids = [row["id"] for row in issue.ready(limit=20)]

    assert child["id"] in ready_ids
    assert parent["id"] not in ready_ids
    assert blocked["id"] not in ready_ids


def test_main_cli_dispatch_supports_issue_and_forum_subcommands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    cli.main(["issue", "new", "Track migration"])
    issues = Issue.from_workdir(tmp_path).list(limit=10)
    assert len(issues) == 1

    cli.main(["forum", "post", "loopfarm:test", "-m", "hello"])
    messages = Forum.from_workdir(tmp_path).read("loopfarm:test", limit=5)
    assert len(messages) == 1
    assert messages[0]["body"] == "hello"
