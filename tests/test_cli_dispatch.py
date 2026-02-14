"""Tests for top-level command dispatch behavior."""

from __future__ import annotations

import pytest

from inshallah.cli import main


def test_main_unknown_single_token_shows_recovery(capsys) -> None:
    with pytest.raises(SystemExit) as ex:
        main(["badcommand"])

    assert ex.value.code == 1
    rendered = capsys.readouterr().out
    assert "Unknown or ambiguous command: badcommand" in rendered
    assert "inshallah --help" in rendered
    assert "inshallah guide" in rendered
    assert "inshallah roles --pretty" in rendered
    assert 'Example: inshallah run "Summarize current ready issues".' in rendered
