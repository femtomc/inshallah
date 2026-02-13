"""Rich streaming formatters for Claude and Codex output."""

from __future__ import annotations

import json

from rich.console import Console
from rich.markup import escape
from rich.text import Text


class ClaudeFormatter:
    """Parses Claude stream-json events and renders via rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._buffer = ""

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
            result_text = event.get("result", "")
            if result_text:
                self.console.print(result_text)
            cost = event.get("cost_usd")
            duration = event.get("duration_ms")
            if cost is not None or duration is not None:
                parts = []
                if cost is not None:
                    parts.append(f"${cost:.4f}")
                if duration is not None:
                    parts.append(f"{duration / 1000:.1f}s")
                self.console.print(
                    Text(" ".join(parts), style="dim italic"),
                )

        elif etype == "tool_use":
            name = event.get("tool", event.get("name", "?"))
            self.console.print(Text(f"  tool: {name}", style="cyan"))

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

        if etype == "message":
            role = event.get("role", "")
            content = event.get("content", "")
            if role == "assistant" and content:
                self.console.print(content, end="")
            elif role == "system" and content:
                self.console.print(Text(content, style="dim"))

        elif etype == "function_call":
            name = event.get("name", "?")
            self.console.print(Text(f"  call: {name}", style="cyan"))

        elif etype == "function_call_output":
            output = event.get("output", "")
            if output:
                truncated = output[:200] + "..." if len(output) > 200 else output
                self.console.print(Text(f"  → {escape(truncated)}", style="dim"))

        elif etype == "error":
            self.console.print(
                Text(f"error: {event.get('message', line)}", style="bold red"),
            )

    def finish(self) -> None:
        self.console.print()


def get_formatter(backend_name: str, console: Console | None = None):
    if backend_name == "claude":
        return ClaudeFormatter(console)
    return CodexFormatter(console)
