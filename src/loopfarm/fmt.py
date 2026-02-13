"""Rich streaming formatters for Claude and Codex output."""

from __future__ import annotations

import json
import re

from rich.console import Console
from rich.text import Text

_SHELL_WRAP_RE = re.compile(r"^/\S+\s+-lc\s+(.+)$", re.DOTALL)
_CD_PREFIX_RE = re.compile(r"^cd\s+\S+\s*&&\s*")


def _strip_shell(cmd: str) -> str:
    """Extract the inner command from /bin/zsh -lc '...' wrappers."""
    m = _SHELL_WRAP_RE.match(cmd)
    if m:
        inner = m.group(1).strip()
        # Strip surrounding quotes
        if (inner.startswith("'") and inner.endswith("'")) or (
            inner.startswith('"') and inner.endswith('"')
        ):
            inner = inner[1:-1]
        cmd = inner
    return _CD_PREFIX_RE.sub("", cmd)


def _truncate(s: str, n: int = 100) -> str:
    return s[:n - 3] + "..." if len(s) > n else s


def _output_summary(output: str) -> str:
    """Summarize command output: line count + first meaningful line."""
    if not output or not output.strip():
        return ""
    lines = output.strip().split("\n")
    first = lines[0].strip()
    if len(lines) == 1:
        return _truncate(first, 60)
    return f"{len(lines)} lines"


class ClaudeFormatter:
    """Parses Claude stream-json events and renders via rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self.console.print(Text(line, style="dim"))
            return

        etype = event.get("type", "")

        if etype == "assistant":
            msg = event.get("message", "")
            if msg:
                self.console.print(msg, end="")

        elif etype == "result":
            cost = event.get("cost_usd")
            duration = event.get("duration_ms")
            parts = []
            if cost is not None:
                parts.append(f"${cost:.4f}")
            if duration is not None:
                parts.append(f"{duration / 1000:.1f}s")
            if parts:
                self.console.print(Text(" ".join(parts), style="dim italic"))

        elif etype == "tool_use":
            name = event.get("tool", event.get("name", "?"))
            inp = event.get("input", {})
            # Build compact one-liner based on tool type
            detail = ""
            if name in ("Read", "Glob", "Grep"):
                detail = inp.get("file_path") or inp.get("pattern") or inp.get("path", "")
            elif name == "Edit":
                detail = inp.get("file_path", "")
            elif name == "Write":
                detail = inp.get("file_path", "")
            elif name == "Bash":
                detail = _truncate(inp.get("command", ""), 80)
            elif name == "Task":
                detail = inp.get("description", "")
            else:
                # Generic: show first string value
                for v in inp.values():
                    if isinstance(v, str) and v:
                        detail = _truncate(v, 60)
                        break
            line_text = f"  {name}"
            if detail:
                line_text += f" {detail}"
            self.console.print(Text(line_text, style="cyan"))

        elif etype == "tool_result":
            pass  # tool results are noisy, skip

        elif etype == "error":
            self.console.print(
                Text(f"error: {event.get('error', line)}", style="bold red"),
            )

    def finish(self) -> None:
        pass


class CodexFormatter:
    """Parses Codex JSONL events and renders via rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self.console.print(Text(line, style="dim"))
            return

        etype = event.get("type", "")
        item = event.get("item", {})
        item_type = item.get("type", "")

        if etype == "item.completed":
            if item_type == "message":
                content = item.get("content", "")
                if content:
                    self.console.print(content)

            elif item_type == "reasoning":
                text = item.get("text", "")
                if text:
                    first = text.split("\n")[0].strip("*").strip()
                    self.console.print(Text(f"  thinking: {_truncate(first, 80)}", style="dim"))

            elif item_type == "command_execution":
                cmd = _strip_shell(item.get("command", ""))
                exit_code = item.get("exit_code")
                output = item.get("aggregated_output", "")
                style = "green" if exit_code == 0 else "red" if exit_code else "cyan"
                summary = _output_summary(output)
                line_text = f"  $ {_truncate(cmd, 80)}"
                if summary:
                    line_text += f"  [{summary}]"
                self.console.print(Text(line_text, style=style))

        elif etype in ("item.started", "thread.started", "turn.started"):
            pass

    def finish(self) -> None:
        self.console.print()


def get_formatter(backend_name: str, console: Console | None = None):
    if backend_name == "claude":
        return ClaudeFormatter(console)
    return CodexFormatter(console)
