"""Tests for top-level command dispatch behavior."""

from __future__ import annotations

import pytest

from loopfarm.cli import main


def test_main_unknown_single_token_shows_recovery(capsys) -> None:
    with pytest.raises(SystemExit) as ex:
        main(["badcommand"])

    assert ex.value.code == 1
    rendered = capsys.readouterr().out
    assert "Unknown or ambiguous command: badcommand" in rendered
    assert "loopfarm --help" in rendered
    assert "loopfarm guide" in rendered
    assert "loopfarm roles --pretty" in rendered
    assert 'Example: loopfarm run "Summarize current ready issues".' in rendered
