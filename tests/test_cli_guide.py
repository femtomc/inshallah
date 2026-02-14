"""Tests for loopfarm guide CLI command."""

from __future__ import annotations

import pytest
from rich.console import Console

from loopfarm.cli import cmd_guide, main


def test_guide_help_has_usage_and_options() -> None:
    console = Console(record=True)

    rc = cmd_guide(["--help"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "Usage: loopfarm guide" in rendered
    assert "--section" in rendered
    assert "--plain" in rendered


def test_guide_plain_output_covers_concepts_and_workflow() -> None:
    console = Console(record=True, force_terminal=False)

    rc = cmd_guide([], console)

    assert rc == 0
    rendered = console.export_text()
    for concept in (
        "issue",
        "parent edge",
        "blocks edge",
        "leaf issue",
        "ready issue",
        "roles",
        "statuses",
        "outcomes",
    ):
        assert concept in rendered
    assert "loopfarm init" in rendered
    assert "loopfarm run" in rendered
    assert "loopfarm issues validate <root-id>" in rendered
    assert "interpretation:" in rendered


def test_guide_section_concepts_only() -> None:
    console = Console(record=True, force_terminal=False)

    rc = cmd_guide(["--section", "concepts", "--plain"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "Core concepts" in rendered
    assert "End-to-end workflow" not in rendered


def test_guide_section_workflow_only() -> None:
    console = Console(record=True, force_terminal=False)

    rc = cmd_guide(["--section", "workflow", "--plain"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "End-to-end workflow" in rendered
    assert "Core concepts" not in rendered
    assert "loopfarm issues ready --root <root-id>" in rendered


def test_guide_plain_flag_forces_plain_renderer() -> None:
    console = Console(record=True, force_terminal=True)

    rc = cmd_guide(["--plain"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "command signal:" in rendered


def test_guide_invalid_section_exits_with_parser_error() -> None:
    with pytest.raises(SystemExit) as ex:
        cmd_guide(["--section", "bad"])
    assert ex.value.code == 2


def test_main_dispatches_guide(capsys) -> None:
    with pytest.raises(SystemExit) as ex:
        main(["guide", "--section", "workflow", "--plain"])
    assert ex.value.code == 0
    assert "End-to-end workflow" in capsys.readouterr().out
