from __future__ import annotations

import io
import json
import re

from rich.console import Console

from loopfarm.fmt import ClaudeFormatter, CodexFormatter, GeminiFormatter, OpenCodeFormatter, PiFormatter


def _console(force_terminal: bool) -> tuple[Console, io.StringIO]:
    out = io.StringIO()
    console = Console(
        file=out,
        force_terminal=force_terminal,
        color_system=None,
        width=120,
    )
    return console, out


def _emit(
    formatter: ClaudeFormatter | CodexFormatter | OpenCodeFormatter | PiFormatter | GeminiFormatter,
    event: dict,
) -> None:
    formatter.process_line(json.dumps(event))


def test_codex_interactive_sections() -> None:
    console, out = _console(force_terminal=True)
    fmt = CodexFormatter(console)

    _emit(
        fmt,
        {
            "type": "item.started",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "/usr/bin/zsh -lc 'echo hi'",
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "/usr/bin/zsh -lc 'echo hi'",
                "aggregated_output": "hi\n",
                "exit_code": 0,
                "status": "completed",
            },
        },
    )

    rendered = out.getvalue()
    assert "stream" in rendered.lower()
    assert "step 1" in rendered.lower()
    assert "status" in rendered.lower()
    assert "$ echo hi" in rendered


def test_codex_noninteractive_plain_output_no_rich_artifacts() -> None:
    console, out = _console(force_terminal=False)
    fmt = CodexFormatter(console)

    _emit(
        fmt,
        {
            "type": "item.started",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "/usr/bin/zsh -lc 'echo hi'",
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "/usr/bin/zsh -lc 'echo hi'",
                "aggregated_output": "hi\n",
                "exit_code": 0,
                "status": "completed",
            },
        },
    )

    rendered = out.getvalue()
    assert "stream: codex" in rendered
    assert "step 1: start: $ echo hi" in rendered
    assert "status: step 1 ok: $ echo hi" in rendered
    assert "[hi]" in rendered
    assert "\x1b[" not in rendered
    assert not re.search(r"[╭╮╰╯│─]", rendered)


def test_codex_renders_reasoning_and_agent_messages() -> None:
    console, out = _console(force_terminal=False)
    fmt = CodexFormatter(console)

    _emit(
        fmt,
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "reasoning",
                "text": "**Planning output changes**",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "agent_message",
                "text": "Applying formatter updates.",
            },
        },
    )

    rendered = out.getvalue()
    assert "status: thinking: Planning output changes" in rendered
    assert "stream: assistant: Applying formatter updates." in rendered


def test_opencode_noninteractive_plain_output() -> None:
    console, out = _console(force_terminal=False)
    fmt = OpenCodeFormatter(console)

    _emit(
        fmt,
        {
            "type": "tool_use",
            "part": {
                "id": "part_1",
                "type": "tool",
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": "/usr/bin/zsh -lc 'echo hi'"},
                    "output": "hi\n",
                },
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "text",
            "part": {
                "id": "part_2",
                "type": "text",
                "text": "Applied OpenCode backend updates.",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "reasoning",
            "part": {
                "id": "part_3",
                "type": "reasoning",
                "text": "**Planning tests**",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "error",
            "error": {
                "name": "RateLimitError",
                "data": {"message": "rate limited"},
            },
        },
    )

    rendered = out.getvalue()
    assert "stream: opencode" in rendered
    assert "step 1: tool bash: echo hi" in rendered
    assert "stream: assistant: Applied OpenCode backend updates." in rendered
    assert "status: thinking: Planning tests" in rendered
    assert "status: error: rate limited" in rendered
    assert "\x1b[" not in rendered
    assert not re.search(r"[╭╮╰╯│─]", rendered)


def test_pi_noninteractive_plain_output() -> None:
    console, out = _console(force_terminal=False)
    fmt = PiFormatter(console)

    _emit(
        fmt,
        {
            "type": "tool_execution_start",
            "toolCallId": "tool_1",
            "toolName": "bash",
            "args": {"command": "/usr/bin/zsh -lc 'echo hi'"},
        },
    )
    _emit(
        fmt,
        {
            "type": "message_update",
            "message": {"role": "assistant"},
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": "Applied pi backend updates.",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "message_update",
            "message": {"role": "assistant"},
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": "**Planning tests**",
            },
        },
    )
    _emit(
        fmt,
        {
            "type": "tool_execution_end",
            "toolCallId": "tool_1",
            "toolName": "bash",
            "result": {"content": [{"type": "text", "text": "hi"}]},
            "isError": False,
        },
    )
    _emit(
        fmt,
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "stopReason": "error",
                "errorMessage": "rate limited",
            },
        },
    )

    rendered = out.getvalue()
    assert "stream: pi" in rendered
    assert "step 1: tool bash: echo hi" in rendered
    assert "stream: assistant: Applied pi backend updates." in rendered
    assert "status: thinking: Planning tests" in rendered
    assert "status: step 1 ok: bash [hi]" in rendered
    assert "status: error: rate limited" in rendered
    assert "\x1b[" not in rendered
    assert not re.search(r"[╭╮╰╯│─]", rendered)


def test_gemini_noninteractive_plain_output() -> None:
    console, out = _console(force_terminal=False)
    fmt = GeminiFormatter(console)

    _emit(fmt, {"type": "init", "model": "gemini-2.5-pro"})
    _emit(
        fmt,
        {
            "type": "tool_use",
            "tool_name": "run_shell_command",
            "tool_id": "tool_1",
            "parameters": {"command": "/usr/bin/zsh -lc 'echo hi'"},
        },
    )
    _emit(
        fmt,
        {
            "type": "message",
            "role": "assistant",
            "content": "Applied Gemini backend updates.",
            "delta": False,
        },
    )
    _emit(
        fmt,
        {
            "type": "tool_result",
            "tool_name": "run_shell_command",
            "tool_id": "tool_1",
            "status": "success",
            "output": "hi\n",
        },
    )
    _emit(
        fmt,
        {
            "type": "result",
            "status": "success",
            "duration_ms": 1200,
            "usage": {"totalTokens": 42},
        },
    )

    rendered = out.getvalue()
    assert "stream: gemini" in rendered
    assert "status: model: gemini-2.5-pro" in rendered
    assert "step 1: tool run_shell_command: echo hi" in rendered
    assert "stream: assistant: Applied Gemini backend updates." in rendered
    assert "status: step 1 ok: run_shell_command [hi]" in rendered
    assert "status: result: success 1.2s tokens=42" in rendered
    assert "\x1b[" not in rendered
    assert not re.search(r"[╭╮╰╯│─]", rendered)


def test_gemini_renders_error_status() -> None:
    console, out = _console(force_terminal=False)
    fmt = GeminiFormatter(console)

    _emit(
        fmt,
        {
            "type": "error",
            "error": {"message": "rate limited"},
        },
    )
    _emit(
        fmt,
        {
            "type": "result",
            "status": "error",
        },
    )

    rendered = out.getvalue()
    assert "status: error: rate limited" in rendered
    assert "status: result: error" in rendered


def test_claude_interactive_sections() -> None:
    console, out = _console(force_terminal=True)
    fmt = ClaudeFormatter(console)

    _emit(
        fmt,
        {
            "type": "tool_use",
            "tool": "Bash",
            "input": {"command": "ls -la"},
        },
    )
    _emit(fmt, {"type": "assistant", "message": "Working on it..."})
    _emit(fmt, {"type": "result", "cost_usd": 0.0012, "duration_ms": 900})
    fmt.finish()

    rendered = out.getvalue()
    assert "stream" in rendered.lower()
    assert "step 1" in rendered.lower()
    assert "tool bash" in rendered.lower()
    assert "status" in rendered.lower()


def test_claude_noninteractive_plain_output_no_rich_artifacts() -> None:
    console, out = _console(force_terminal=False)
    fmt = ClaudeFormatter(console)

    _emit(
        fmt,
        {
            "type": "tool_use",
            "tool": "Read",
            "input": {"file_path": "src/loopfarm/fmt.py"},
        },
    )
    _emit(fmt, {"type": "error", "error": "boom"})

    rendered = out.getvalue()
    assert "stream: claude" in rendered
    assert "step 1: tool Read: src/loopfarm/fmt.py" in rendered
    assert "status: error: boom" in rendered
    assert "\x1b[" not in rendered
    assert not re.search(r"[╭╮╰╯│─]", rendered)
