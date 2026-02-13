"""Rich streaming formatters for Claude, Codex, OpenCode, pi, and Gemini output."""

from __future__ import annotations

import json
import re

from rich.console import Console
from rich.panel import Panel
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


def _is_interactive(console: Console) -> bool:
    return bool(console.is_terminal and not console.is_dumb_terminal)


def _command_style(exit_code: object) -> str:
    if exit_code == 0:
        return "green"
    if isinstance(exit_code, int):
        return "red"
    return "yellow"


def _message_text(item: dict) -> str:
    text = item.get("text")
    if isinstance(text, str) and text:
        return text

    content = item.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                if part:
                    parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            ptext = part.get("text")
            if isinstance(ptext, str) and ptext:
                parts.append(ptext)
                continue
            pcontent = part.get("content")
            if isinstance(pcontent, str) and pcontent:
                parts.append(pcontent)
        return "\n".join(parts)

    return ""


class _BaseFormatter:
    def __init__(self, backend_name: str, console: Console | None = None) -> None:
        self.backend_name = backend_name
        self.console = console or Console()
        self.interactive = _is_interactive(self.console)
        self._stream_announced = False

    def _announce_stream(self) -> None:
        if self._stream_announced:
            return
        self._stream_announced = True
        if self.interactive:
            self.console.print(
                Panel.fit(
                    Text(f"{self.backend_name} live stream", style="bold"),
                    title="stream",
                    border_style="blue",
                )
            )
        else:
            self.console.print(f"stream: {self.backend_name}")

    def _print_raw_line(self, line: str) -> None:
        if self.interactive:
            self.console.print(Text(line, style="dim"))
        else:
            self.console.print(line, markup=False)

    def _print_step(self, step: int, message: str, *, style: str = "cyan") -> None:
        if self.interactive:
            self.console.print(
                Panel.fit(
                    Text(message),
                    title=f"step {step}",
                    border_style=style,
                )
            )
        else:
            self.console.print(f"step {step}: {message}", markup=False)

    def _print_status(self, message: str, *, style: str = "dim") -> None:
        if self.interactive:
            self.console.print(
                Panel.fit(
                    Text(message),
                    title="status",
                    border_style=style,
                )
            )
        else:
            self.console.print(f"status: {message}", markup=False)

    def _print_stream(self, message: str, *, style: str = "green") -> None:
        if self.interactive:
            self.console.print(
                Panel.fit(
                    Text(message),
                    title="stream",
                    border_style=style,
                )
            )
        else:
            self.console.print(f"stream: {message}", markup=False)


class ClaudeFormatter(_BaseFormatter):
    """Parses Claude stream-json events and renders stream/step/status sections."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__("claude", console)
        self._tool_step = 0
        self._assistant_open = False
        self._assistant_label_printed = False

    def _flush_assistant(self) -> None:
        if self._assistant_open:
            self.console.print()
            self._assistant_open = False
            self._assistant_label_printed = False

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        self._announce_stream()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._flush_assistant()
            self._print_raw_line(line)
            return

        etype = event.get("type", "")

        if etype == "assistant":
            msg = event.get("message", "")
            if msg:
                if not self._assistant_label_printed:
                    if self.interactive:
                        self.console.print(Text("assistant:", style="bold green"))
                    else:
                        self.console.print("assistant: ", end="", markup=False)
                    self._assistant_label_printed = True
                self.console.print(msg, end="", markup=False)
                self._assistant_open = True

        elif etype == "result":
            self._flush_assistant()
            cost = event.get("cost_usd")
            duration = event.get("duration_ms")
            parts = []
            if cost is not None:
                parts.append(f"${cost:.4f}")
            if duration is not None:
                parts.append(f"{duration / 1000:.1f}s")
            if parts:
                self._print_status(" ".join(parts), style="green")

        elif etype == "tool_use":
            self._flush_assistant()
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
            self._tool_step += 1
            line_text = f"tool {name}"
            if detail:
                line_text += f": {detail}"
            self._print_step(self._tool_step, line_text, style="cyan")

        elif etype == "tool_result":
            pass  # tool results are noisy, skip

        elif etype == "error":
            self._flush_assistant()
            self._print_status(f"error: {event.get('error', line)}", style="red")

    def finish(self) -> None:
        self._flush_assistant()


class CodexFormatter(_BaseFormatter):
    """Parses Codex JSONL events and renders stream/step/status sections."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__("codex", console)
        self._next_step = 0
        self._item_step: dict[str, int] = {}

    def _step_for(self, item_id: str | None) -> int:
        if not item_id:
            self._next_step += 1
            return self._next_step
        existing = self._item_step.get(item_id)
        if existing is not None:
            return existing
        self._next_step += 1
        self._item_step[item_id] = self._next_step
        return self._next_step

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        self._announce_stream()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._print_raw_line(line)
            return

        etype = event.get("type", "")
        item = event.get("item", {})
        item_type = item.get("type", "")
        item_id = item.get("id")

        if etype == "item.started" and item_type == "command_execution":
            step = self._step_for(item_id)
            cmd = _strip_shell(item.get("command", ""))
            self._print_step(step, f"start: $ {_truncate(cmd, 120)}", style="cyan")

        elif etype == "item.completed":
            if item_type in ("message", "agent_message"):
                content = _message_text(item)
                if content:
                    self._print_stream(f"assistant: {content}", style="green")

            elif item_type == "reasoning":
                text = item.get("text", "")
                if text:
                    first = text.split("\n")[0].strip("*").strip()
                    self._print_status(
                        f"thinking: {_truncate(first, 80)}",
                        style="magenta",
                    )

            elif item_type == "command_execution":
                step = self._step_for(item_id)
                cmd = _strip_shell(item.get("command", ""))
                exit_code = item.get("exit_code")
                output = item.get("aggregated_output", "")
                summary = _output_summary(output)
                line_text = f"step {step} "
                if exit_code == 0:
                    line_text += "ok"
                elif isinstance(exit_code, int):
                    line_text += f"exit={exit_code}"
                else:
                    line_text += "done"
                line_text += f": $ {_truncate(cmd, 120)}"
                if summary:
                    line_text += f"  [{summary}]"
                self._print_status(line_text, style=_command_style(exit_code))

        elif etype == "thread.started":
            self._print_status("thread started", style="dim")

        elif etype == "turn.started":
            self._print_status("turn started", style="dim")

        elif etype == "error":
            self._print_status(f"error: {event.get('error', line)}", style="red")

    def finish(self) -> None:
        return


class OpenCodeFormatter(_BaseFormatter):
    """Parses OpenCode run --format json events and renders stream/step/status sections."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__("opencode", console)
        self._step = 0

    def _next_step(self) -> int:
        self._step += 1
        return self._step

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        self._announce_stream()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._print_raw_line(line)
            return

        etype = event.get("type", "")

        if etype == "tool_use":
            part = event.get("part", {})
            tool = part.get("tool", "?")
            state = part.get("state", {})
            tool_input = state.get("input", {}) if isinstance(state, dict) else {}
            if not isinstance(tool_input, dict):
                tool_input = {}

            detail = ""
            if tool in ("read", "write", "edit"):
                detail = tool_input.get("filePath", "")
            elif tool in ("glob", "grep"):
                detail = tool_input.get("pattern", "")
            elif tool == "bash":
                detail = _truncate(_strip_shell(tool_input.get("command", "")), 80)
            elif tool == "task":
                detail = tool_input.get("description", "")
            elif isinstance(tool_input, dict):
                for value in tool_input.values():
                    if isinstance(value, str) and value:
                        detail = _truncate(value, 60)
                        break

            step = self._next_step()
            message = f"tool {tool}"
            if detail:
                message += f": {detail}"
            self._print_step(step, message, style="cyan")
            return

        if etype == "text":
            part = event.get("part", {})
            text = part.get("text", "")
            if isinstance(text, str):
                text = text.strip()
                if text:
                    self._print_stream(f"assistant: {text}", style="green")
            return

        if etype == "reasoning":
            part = event.get("part", {})
            text = part.get("text", "")
            if isinstance(text, str):
                text = text.strip()
                if text:
                    first = text.split("\n")[0].strip("*").strip()
                    self._print_status(f"thinking: {_truncate(first, 80)}", style="magenta")
            return

        if etype == "step_start":
            self._print_status("step started", style="dim")
            return

        if etype == "step_finish":
            self._print_status("step finished", style="dim")
            return

        if etype == "error":
            err = event.get("error", line)
            if isinstance(err, dict):
                data = err.get("data", {})
                if isinstance(data, dict) and isinstance(data.get("message"), str):
                    msg = data["message"]
                elif isinstance(err.get("message"), str):
                    msg = err["message"]
                elif isinstance(err.get("name"), str):
                    msg = err["name"]
                else:
                    msg = json.dumps(err)
            else:
                msg = str(err)
            self._print_status(f"error: {msg}", style="red")

    def finish(self) -> None:
        return


class GeminiFormatter(_BaseFormatter):
    """Parses Gemini --output-format stream-json events."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__("gemini", console)
        self._next_step = 0
        self._tool_step: dict[str, int] = {}

    def _step_for(self, tool_id: str | None) -> int:
        if not tool_id:
            self._next_step += 1
            return self._next_step
        existing = self._tool_step.get(tool_id)
        if existing is not None:
            return existing
        self._next_step += 1
        self._tool_step[tool_id] = self._next_step
        return self._next_step

    def _tool_detail(self, tool_name: str, params: object) -> str:
        if not isinstance(params, dict):
            return ""

        if tool_name in ("read_file", "write_file", "replace"):
            for key in ("path", "file_path"):
                value = params.get(key)
                if isinstance(value, str) and value:
                    return value

        if tool_name in ("glob", "grep", "search_file_content"):
            for key in ("pattern", "path", "query"):
                value = params.get(key)
                if isinstance(value, str) and value:
                    return value

        if tool_name in ("run_shell_command", "bash"):
            for key in ("command", "cmd"):
                command = params.get(key)
                if isinstance(command, str) and command:
                    return _truncate(_strip_shell(command), 80)

        for value in params.values():
            if isinstance(value, str) and value:
                return _truncate(value, 60)
        return ""

    def _tool_output_summary(self, output: object) -> str:
        if isinstance(output, str):
            return _output_summary(output)
        if isinstance(output, dict):
            for key in ("content", "output", "text", "message"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return _output_summary(value)
        return ""

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        self._announce_stream()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._print_raw_line(line)
            return

        etype = event.get("type", "")

        if etype == "init":
            model = event.get("model")
            if isinstance(model, str) and model:
                self._print_status(f"model: {model}", style="dim")
            return

        if etype == "message":
            if event.get("role") != "assistant":
                return
            content = event.get("content")
            if isinstance(content, str) and content:
                self._print_stream(f"assistant: {content}", style="green")
            return

        if etype == "tool_use":
            tool_id = event.get("tool_id")
            step = self._step_for(tool_id if isinstance(tool_id, str) else None)
            tool_name = event.get("tool_name", "?")
            if not isinstance(tool_name, str):
                tool_name = "?"
            detail = self._tool_detail(tool_name, event.get("parameters", {}))
            message = f"tool {tool_name}"
            if detail:
                message += f": {detail}"
            self._print_step(step, message, style="cyan")
            return

        if etype == "tool_result":
            tool_id = event.get("tool_id")
            step = self._step_for(tool_id if isinstance(tool_id, str) else None)
            tool_name = event.get("tool_name", "?")
            if not isinstance(tool_name, str):
                tool_name = "?"
            status = event.get("status")
            status_text = status.lower() if isinstance(status, str) else ""
            is_error = status_text not in ("success", "ok")
            summary = self._tool_output_summary(event.get("output"))
            message = f"step {step} {'error' if is_error else 'ok'}: {tool_name}"
            if summary:
                message += f" [{summary}]"
            self._print_status(message, style="red" if is_error else "green")
            return

        if etype == "error":
            err = event.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or err.get("details") or err)
            elif isinstance(err, str) and err:
                msg = err
            else:
                msg = str(event.get("message") or line)
            self._print_status(f"error: {msg}", style="red")
            return

        if etype == "result":
            status = event.get("status")
            if not isinstance(status, str):
                status = "unknown"
            style = "green" if status.lower() == "success" else "red"
            parts = [f"result: {status}"]
            duration = event.get("duration_ms")
            if isinstance(duration, (int, float)):
                parts.append(f"{duration / 1000:.1f}s")
            usage = event.get("usage")
            if isinstance(usage, dict):
                total_tokens = usage.get("totalTokens")
                if isinstance(total_tokens, int):
                    parts.append(f"tokens={total_tokens}")
            self._print_status(" ".join(parts), style=style)
            return

    def finish(self) -> None:
        return


class PiFormatter(_BaseFormatter):
    """Parses pi --mode json events and renders stream/step/status sections."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__("pi", console)
        self._next_step = 0
        self._tool_step: dict[str, int] = {}

    def _step_for(self, tool_call_id: str | None) -> int:
        if not tool_call_id:
            self._next_step += 1
            return self._next_step
        existing = self._tool_step.get(tool_call_id)
        if existing is not None:
            return existing
        self._next_step += 1
        self._tool_step[tool_call_id] = self._next_step
        return self._next_step

    def _tool_detail(self, tool_name: str, args: object) -> str:
        if not isinstance(args, dict):
            return ""

        if tool_name in ("read", "write", "edit"):
            for key in ("path", "filePath", "targetPath"):
                value = args.get(key)
                if isinstance(value, str) and value:
                    return value

        if tool_name in ("grep", "find"):
            for key in ("pattern", "path"):
                value = args.get(key)
                if isinstance(value, str) and value:
                    return value

        if tool_name == "bash":
            command = args.get("command")
            if isinstance(command, str) and command:
                return _truncate(_strip_shell(command), 80)

        for value in args.values():
            if isinstance(value, str) and value:
                return _truncate(value, 60)
        return ""

    def _tool_output_summary(self, result: object) -> str:
        if not isinstance(result, dict):
            return ""
        content = result.get("content")
        if not isinstance(content, list):
            return ""
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return _output_summary(text.strip())
        return ""

    def process_line(self, line: str) -> None:
        if not line.strip():
            return
        self._announce_stream()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._print_raw_line(line)
            return

        etype = event.get("type", "")

        if etype == "tool_execution_start":
            tool_call_id = event.get("toolCallId")
            step = self._step_for(tool_call_id if isinstance(tool_call_id, str) else None)
            tool_name = event.get("toolName", "?")
            if not isinstance(tool_name, str):
                tool_name = "?"
            detail = self._tool_detail(tool_name, event.get("args", {}))
            message = f"tool {tool_name}"
            if detail:
                message += f": {detail}"
            self._print_step(step, message, style="cyan")
            return

        if etype == "tool_execution_end":
            tool_call_id = event.get("toolCallId")
            step = self._step_for(tool_call_id if isinstance(tool_call_id, str) else None)
            tool_name = event.get("toolName", "?")
            if not isinstance(tool_name, str):
                tool_name = "?"
            is_error = bool(event.get("isError"))
            summary = self._tool_output_summary(event.get("result", {}))
            message = f"step {step} {'error' if is_error else 'ok'}: {tool_name}"
            if summary:
                message += f" [{summary}]"
            self._print_status(message, style="red" if is_error else "green")
            return

        if etype == "message_update":
            assistant_event = event.get("assistantMessageEvent", {})
            if not isinstance(assistant_event, dict):
                return
            assistant_event_type = assistant_event.get("type", "")
            if assistant_event_type == "text_delta":
                delta = assistant_event.get("delta", "")
                if isinstance(delta, str) and delta:
                    self._print_stream(f"assistant: {delta}", style="green")
                return
            if assistant_event_type == "thinking_delta":
                delta = assistant_event.get("delta", "")
                if isinstance(delta, str):
                    first = delta.split("\n")[0].strip("*").strip()
                    if first:
                        self._print_status(
                            f"thinking: {_truncate(first, 80)}",
                            style="magenta",
                        )
                return
            if assistant_event_type == "error":
                error_value = assistant_event.get("error", {})
                message = "assistant error"
                if isinstance(error_value, dict):
                    for key in ("errorMessage", "message"):
                        value = error_value.get(key)
                        if isinstance(value, str) and value:
                            message = value
                            break
                self._print_status(f"error: {message}", style="red")
                return

        if etype == "message_end":
            message = event.get("message", {})
            if not isinstance(message, dict):
                return
            if message.get("role") != "assistant":
                return
            stop_reason = message.get("stopReason")
            if stop_reason in ("error", "aborted"):
                error_message = message.get("errorMessage")
                if not isinstance(error_message, str) or not error_message:
                    error_message = f"assistant {stop_reason}"
                self._print_status(f"error: {error_message}", style="red")
            return

        if etype == "auto_retry_start":
            attempt = event.get("attempt")
            max_attempts = event.get("maxAttempts")
            if isinstance(attempt, int) and isinstance(max_attempts, int):
                self._print_status(f"retrying ({attempt}/{max_attempts})", style="yellow")
            return

        if etype == "auto_retry_end":
            if event.get("success") is False:
                final_error = event.get("finalError")
                if not isinstance(final_error, str) or not final_error:
                    final_error = "retry failed"
                self._print_status(f"error: {final_error}", style="red")
            return

    def finish(self) -> None:
        return


def get_formatter(backend_name: str, console: Console | None = None):
    if backend_name == "claude":
        return ClaudeFormatter(console)
    if backend_name == "opencode":
        return OpenCodeFormatter(console)
    if backend_name == "gemini":
        return GeminiFormatter(console)
    if backend_name == "pi":
        return PiFormatter(console)
    return CodexFormatter(console)
