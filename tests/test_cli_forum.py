"""Tests for loopfarm forum CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from loopfarm.cli import cmd_forum


def _setup(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    lf = tmp_path / ".loopfarm"
    lf.mkdir()
    (lf / "issues.jsonl").touch()
    (lf / "forum.jsonl").touch()


def _run(tmp_path: Path, argv: list[str], capsys) -> tuple[int, object]:
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_forum(argv)
    raw = capsys.readouterr().out
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    return rc, parsed


class TestPostRead:
    def test_post_and_read(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)

        rc, out = _run(
            tmp_path,
            ["post", "issue:abc", "-m", "hello", "--author", "worker"],
            capsys,
        )
        assert rc == 0
        assert out["topic"] == "issue:abc"
        assert out["author"] == "worker"

        rc, out = _run(tmp_path, ["read", "issue:abc"], capsys)
        assert rc == 0
        assert len(out) == 1
        assert out[0]["body"] == "hello"

    def test_topics(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)

        _run(tmp_path, ["post", "issue:a", "-m", "one"], capsys)
        _run(tmp_path, ["post", "issue:b", "-m", "two"], capsys)

        rc, out = _run(tmp_path, ["topics", "--prefix", "issue:"], capsys)
        assert rc == 0
        assert {row["topic"] for row in out} == {"issue:a", "issue:b"}


class TestDispatcher:
    def test_no_args(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, [], capsys)
        assert rc == 0
        assert "loopfarm forum" in out

    def test_unknown_subcommand(self, tmp_path: Path, capsys) -> None:
        _setup(tmp_path)
        rc, out = _run(tmp_path, ["bogus"], capsys)
        assert rc == 1
        assert "error" in out
