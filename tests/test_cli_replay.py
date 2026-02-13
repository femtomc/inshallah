from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console

from loopfarm.cli import cmd_replay


def test_replay_help_mentions_gemini_backend(tmp_path: Path) -> None:
    (tmp_path / ".loopfarm" / "logs").mkdir(parents=True)
    console = Console(record=True)

    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path):
        rc = cmd_replay(["--help"], console)

    assert rc == 0
    rendered = console.export_text()
    assert "--backend codex|claude|opencode|pi|gemini" in rendered


def test_replay_uses_gemini_formatter(tmp_path: Path) -> None:
    logs_dir = tmp_path / ".loopfarm" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "loopfarm-test123.jsonl").write_text('{"type":"text","part":{"text":"hello"}}\n')

    console = Console(record=True)
    formatter = MagicMock()

    with patch("loopfarm.cli._find_repo_root", return_value=tmp_path), patch(
        "loopfarm.cli.get_formatter",
        return_value=formatter,
    ) as mock_get_formatter:
        rc = cmd_replay(["loopfarm-test123", "--backend", "gemini"], console)

    assert rc == 0
    mock_get_formatter.assert_called_with("gemini", console)
    formatter.process_line.assert_called_once_with('{"type":"text","part":{"text":"hello"}}')
    formatter.finish.assert_called_once()
