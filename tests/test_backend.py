from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loopfarm.backend import GeminiBackend, OpenCodeBackend, PiBackend, get_backend


def test_get_backend_opencode() -> None:
    backend = get_backend("opencode")
    assert isinstance(backend, OpenCodeBackend)


def test_get_backend_pi() -> None:
    backend = get_backend("pi")
    assert isinstance(backend, PiBackend)


def test_get_backend_gemini() -> None:
    backend = get_backend("gemini")
    assert isinstance(backend, GeminiBackend)


def test_opencode_build_argv() -> None:
    backend = OpenCodeBackend()

    argv = backend.build_argv(
        "Implement this issue end-to-end.",
        "openai/gpt-5",
        "high",
        Path("/tmp/workspace"),
    )

    assert argv == [
        "opencode",
        "run",
        "--format",
        "json",
        "--dir",
        "/tmp/workspace",
        "--model",
        "openai/gpt-5",
        "--variant",
        "high",
        "Implement this issue end-to-end.",
    ]


def test_pi_build_argv() -> None:
    backend = PiBackend()

    argv = backend.build_argv(
        "Implement this issue end-to-end.",
        "openai/gpt-5",
        "high",
        Path("/tmp/workspace"),
    )

    assert argv == [
        "pi",
        "--mode",
        "json",
        "--no-session",
        "--model",
        "openai/gpt-5",
        "--thinking",
        "high",
        "Implement this issue end-to-end.",
    ]


def test_gemini_build_argv() -> None:
    backend = GeminiBackend()

    argv = backend.build_argv(
        "Implement this issue end-to-end.",
        "gemini-2.5-pro",
        "high",
        Path("/tmp/workspace"),
    )

    assert argv == [
        "gemini",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-2.5-pro",
        "--yolo",
        "--prompt",
        "Implement this issue end-to-end.",
    ]


def test_pi_run_maps_stream_error_to_nonzero_exit() -> None:
    backend = PiBackend()
    on_line = MagicMock()

    with patch("loopfarm.backend.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline.side_effect = [
            '{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"boom"}}\n',
            "",
        ]
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        rc = backend.run(
            "Implement this issue end-to-end.",
            "openai/gpt-5",
            "high",
            Path("/tmp/workspace"),
            on_line=on_line,
        )

    assert rc == 1
    on_line.assert_called_once_with(
        '{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"boom"}}'
    )


def test_pi_run_keeps_process_exit_code() -> None:
    backend = PiBackend()

    with patch("loopfarm.backend.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline.side_effect = [
            '{"type":"message_end","message":{"role":"assistant","stopReason":"stop"}}\n',
            "",
        ]
        proc.poll.return_value = 7
        proc.wait.return_value = 7
        mock_popen.return_value = proc

        rc = backend.run(
            "Implement this issue end-to-end.",
            "openai/gpt-5",
            "high",
            Path("/tmp/workspace"),
        )

    assert rc == 7


def test_gemini_run_maps_result_failure_to_nonzero_exit() -> None:
    backend = GeminiBackend()
    on_line = MagicMock()

    with patch("loopfarm.backend.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline.side_effect = [
            '{"type":"message","role":"assistant","content":"Working...","delta":true}\n',
            '{"type":"result","status":"error"}\n',
            "",
        ]
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        rc = backend.run(
            "Implement this issue end-to-end.",
            "gemini-2.5-pro",
            "high",
            Path("/tmp/workspace"),
            on_line=on_line,
        )

    assert rc == 1
    assert on_line.call_count == 2


def test_unknown_backend_error_lists_opencode_pi_and_gemini() -> None:
    with pytest.raises(ValueError) as exc:
        get_backend("unknown")

    assert "opencode" in str(exc.value)
    assert "pi" in str(exc.value)
    assert "gemini" in str(exc.value)
