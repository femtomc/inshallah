"""Tests for inshallah issues CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from inshallah.cli import cmd_issues


def _setup(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    lf = tmp_path / ".inshallah"
    lf.mkdir()
    (lf / "issues.jsonl").touch()
    (lf / "forum.jsonl").touch()


def _run(tmp_path: Path, argv: list[str], capsys) -> tuple[int, object]:
    with patch("inshallah.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_issues(argv)
    raw = capsys.readouterr().out
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    return rc, parsed


# -- list ------------------------------------------------------------------


class TestList:
    def test_empty(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["list"], capsys)
        assert rc == 0
        assert out == []

    def test_filter_status(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        store.create("open one", tags=["node:agent"])
        i2 = store.create("closed one", tags=["node:agent"])
        store.close(i2["id"])

        rc, out = _run(tmp_path, ["list", "--status", "closed"], capsys)
        assert rc == 0
        assert len(out) == 1
        assert out[0]["status"] == "closed"

    def test_filter_tag(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        store.create("tagged", tags=["node:agent", "special"])
        store.create("untagged", tags=["node:agent"])

        rc, out = _run(tmp_path, ["list", "--tag", "special"], capsys)
        assert rc == 0
        assert len(out) == 1
        assert "special" in out[0]["tags"]

    def test_filter_root(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        root = store.create("root", tags=["node:agent", "node:root"])
        child = store.create("child", tags=["node:agent"])
        store.add_dep(child["id"], "parent", root["id"])
        store.create("orphan", tags=["node:agent"])

        rc, out = _run(tmp_path, ["list", "--root", root["id"]], capsys)
        assert rc == 0
        ids = {i["id"] for i in out}
        assert root["id"] in ids
        assert child["id"] in ids
        assert len(ids) == 2


# -- get -------------------------------------------------------------------


class TestGet:
    def test_found(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        issue = store.create("test", tags=["node:agent"])

        rc, out = _run(tmp_path, ["get", issue["id"]], capsys)
        assert rc == 0
        assert out["id"] == issue["id"]
        assert out["title"] == "test"

    def test_not_found(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["get", "nonexistent"], capsys)
        assert rc == 1
        assert "error" in out

    def test_missing_id(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["get"], capsys)
        assert rc == 0
        assert "inshallah issues get" in out


# -- create ----------------------------------------------------------------


class TestCreate:
    def test_basic(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["create", "New issue"], capsys)
        assert rc == 0
        assert out["title"] == "New issue"
        assert "node:agent" in out["tags"]
        assert out["status"] == "open"

    def test_with_body_and_role(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(
            tmp_path,
            ["create", "Task", "--body", "Details here", "--role", "worker", "--priority", "1"],
            capsys,
        )
        assert rc == 0
        assert out["body"] == "Details here"
        assert out["execution_spec"] == {"role": "worker"}
        assert out["priority"] == 1

    def test_with_parent(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        parent = store.create("parent", tags=["node:agent", "node:root"])

        rc, out = _run(
            tmp_path,
            ["create", "child", "--parent", parent["id"]],
            capsys,
        )
        assert rc == 0
        assert any(d["type"] == "parent" and d["target"] == parent["id"] for d in out["deps"])

    def test_auto_tag(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["create", "No tags", "-t", "custom"], capsys)
        assert rc == 0
        assert "node:agent" in out["tags"]
        assert "custom" in out["tags"]

    def test_missing_title(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["create"], capsys)
        assert rc == 1
        assert "error" in out

    def test_bad_parent_does_not_create_issue(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")

        rc, out = _run(tmp_path, ["create", "child", "--parent", "missing"], capsys)
        assert rc == 1
        assert "error" in out
        assert store.list() == []


# -- close -----------------------------------------------------------------


class TestClose:
    def test_default_outcome(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        issue = store.create("test", tags=["node:agent"])

        rc, out = _run(tmp_path, ["close", issue["id"]], capsys)
        assert rc == 0
        assert out["status"] == "closed"
        assert out["outcome"] == "success"

    def test_custom_outcome(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        issue = store.create("test", tags=["node:agent"])

        rc, out = _run(tmp_path, ["close", issue["id"], "--outcome", "expanded"], capsys)
        assert rc == 0
        assert out["outcome"] == "expanded"

    def test_not_found(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["close", "nonexistent"], capsys)
        assert rc == 1
        assert "error" in out

    def test_missing_id(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["close"], capsys)
        assert rc == 0
        assert "inshallah issues close" in out


# -- update/claim/open ------------------------------------------------------


class TestUpdateClaimOpen:
    def test_update_fields(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        issue = store.create("task", tags=["node:agent"])

        rc, out = _run(
            tmp_path,
            [
                "update",
                issue["id"],
                "--status",
                "in_progress",
                "--add-tag",
                "backend",
                "--role",
                "worker",
                "--priority",
                "2",
            ],
            capsys,
        )

        assert rc == 0
        assert out["status"] == "in_progress"
        assert "backend" in out["tags"]
        assert out["execution_spec"]["role"] == "worker"
        assert out["priority"] == 2

    def test_claim_then_open(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        issue = store.create("task", tags=["node:agent"])

        rc, out = _run(tmp_path, ["claim", issue["id"]], capsys)
        assert rc == 0
        assert out["status"] == "in_progress"

        rc, out = _run(tmp_path, ["open", issue["id"]], capsys)
        assert rc == 0
        assert out["status"] == "open"
        assert out["outcome"] is None


# -- dep -------------------------------------------------------------------


class TestDep:
    def test_blocks(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        a = store.create("a", tags=["node:agent"])
        b = store.create("b", tags=["node:agent"])

        rc, out = _run(tmp_path, ["dep", a["id"], "blocks", b["id"]], capsys)
        assert rc == 0
        assert out["ok"] is True

    def test_parent(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        child = store.create("child", tags=["node:agent"])
        parent = store.create("parent", tags=["node:agent"])

        rc, out = _run(tmp_path, ["dep", child["id"], "parent", parent["id"]], capsys)
        assert rc == 0
        assert out["ok"] is True

    def test_invalid_type(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["dep", "a", "depends_on", "b"], capsys)
        assert rc == 1
        assert "error" in out

    def test_not_enough_args(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["dep", "a"], capsys)
        assert rc == 1
        assert "error" in out

    def test_undep(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        a = store.create("a", tags=["node:agent"])
        b = store.create("b", tags=["node:agent"])
        store.add_dep(a["id"], "blocks", b["id"])

        rc, out = _run(tmp_path, ["undep", a["id"], "blocks", b["id"]], capsys)
        assert rc == 0
        assert out["ok"] is True


# -- ready -----------------------------------------------------------------


class TestReady:
    def test_empty(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["ready"], capsys)
        assert rc == 0
        assert out == []

    def test_with_root(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        root = store.create("root", tags=["node:agent", "node:root"])
        child = store.create("child", tags=["node:agent"])
        store.add_dep(child["id"], "parent", root["id"])

        rc, out = _run(tmp_path, ["ready", "--root", root["id"]], capsys)
        assert rc == 0
        ids = [i["id"] for i in out]
        assert child["id"] in ids

    def test_blocked_excluded(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore
        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        root = store.create("root", tags=["node:agent", "node:root"])
        a = store.create("a", tags=["node:agent"])
        b = store.create("b", tags=["node:agent"])
        store.add_dep(a["id"], "parent", root["id"])
        store.add_dep(b["id"], "parent", root["id"])
        store.add_dep(a["id"], "blocks", b["id"])

        rc, out = _run(tmp_path, ["ready", "--root", root["id"]], capsys)
        assert rc == 0
        ids = [i["id"] for i in out]
        assert a["id"] in ids
        assert b["id"] not in ids


# -- children/validate ------------------------------------------------------


class TestChildrenValidate:
    def test_children(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        root = store.create("root", tags=["node:agent", "node:root"])
        child = store.create("child", tags=["node:agent"])
        store.add_dep(child["id"], "parent", root["id"])

        rc, out = _run(tmp_path, ["children", root["id"]], capsys)
        assert rc == 0
        ids = [i["id"] for i in out]
        assert child["id"] in ids

    def test_validate(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        from inshallah.store import IssueStore

        store = IssueStore(tmp_path / ".inshallah" / "issues.jsonl")
        root = store.create("root", tags=["node:agent", "node:root"])
        child = store.create("child", tags=["node:agent"])
        store.add_dep(child["id"], "parent", root["id"])

        rc, out = _run(tmp_path, ["validate", root["id"]], capsys)
        assert rc == 0
        assert out["is_final"] is False
        assert "reason" in out


# -- dispatcher ------------------------------------------------------------


class TestDispatcher:
    def test_no_args(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, [], capsys)
        assert rc == 0
        assert "inshallah issues" in out

    def test_unknown_subcommand(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["bogus"], capsys)
        assert rc == 1
        assert "error" in out

    def test_pretty_flag(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, _ = _run(tmp_path, ["--pretty", "list"], capsys)
        assert rc == 0
