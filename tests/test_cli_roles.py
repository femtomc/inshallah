"""Tests for loopfarm roles CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from loopfarm.cli import cmd_roles


def _setup(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".loopfarm").mkdir()


def test_no_roles(tmp_path: Path, capsys) -> None:
    _setup(tmp_path)
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_roles([], None)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == []


def test_one_role(tmp_path: Path, capsys) -> None:
    _setup(tmp_path)
    roles_dir = tmp_path / ".loopfarm" / "roles"
    roles_dir.mkdir()
    (roles_dir / "worker.md").write_text(
        "---\ndescription: Frontmatter worker summary\ncli: codex\nmodel: gpt-5.3\nreasoning: xhigh\n---\nA worker role.\n"
    )
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_roles([], None)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1
    assert out[0]["name"] == "worker"
    assert out[0]["cli"] == "codex"
    assert out[0]["model"] == "gpt-5.3"
    assert out[0]["reasoning"] == "xhigh"
    assert out[0]["prompt_path"] == ".loopfarm/roles/worker.md"
    assert out[0]["description"] == "Frontmatter worker summary"
    assert out[0]["description_source"] == "frontmatter"


def test_multiple_roles_sorted(tmp_path: Path, capsys) -> None:
    _setup(tmp_path)
    roles_dir = tmp_path / ".loopfarm" / "roles"
    roles_dir.mkdir()
    (roles_dir / "worker.md").write_text("---\ncli: codex\n---\nWorker.\n")
    (roles_dir / "analyst.md").write_text("---\ncli: claude\nmodel: opus\n---\nAnalyst.\n")
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_roles([], None)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 2
    assert out[0]["name"] == "analyst"
    assert out[1]["name"] == "worker"


def test_pretty_flag(tmp_path: Path, capsys) -> None:
    _setup(tmp_path)
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_roles(["--pretty"], None)
    assert rc == 0
    raw = capsys.readouterr().out
    # Pretty output has newlines and indentation
    assert "[\n" in raw or raw.strip() == "[]"
    json.loads(raw)  # Still valid JSON


def test_description_falls_back_to_body(tmp_path: Path, capsys) -> None:
    _setup(tmp_path)
    roles_dir = tmp_path / ".loopfarm" / "roles"
    roles_dir.mkdir()
    (roles_dir / "worker.md").write_text("---\ncli: codex\n---\nBody summary.\n")
    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_roles([], None)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["description"] == "Body summary."
    assert out[0]["description_source"] == "body"
