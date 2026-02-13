"""Backend runners for Claude and Codex CLI tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


class Backend:
    name: str

    def build_argv(
        self,
        prompt: str,
        model: str,
        reasoning: str,
        cwd: Path,
    ) -> list[str]:
        raise NotImplementedError

    def run(
        self,
        prompt: str,
        model: str,
        reasoning: str,
        cwd: Path,
        on_line: Callable[[str], None] | None = None,
        tee_path: Path | None = None,
    ) -> int:
        argv = self.build_argv(prompt, model, reasoning, cwd)
        tee_fh = open(tee_path, "w") if tee_path else None
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if not line:
                    continue
                line = line.rstrip("\n")
                if on_line:
                    on_line(line)
                if tee_fh:
                    tee_fh.write(line + "\n")
                    tee_fh.flush()
            return proc.wait()
        finally:
            if tee_fh:
                tee_fh.close()


class ClaudeBackend(Backend):
    name = "claude"

    def build_argv(
        self,
        prompt: str,
        model: str,
        reasoning: str,
        cwd: Path,
    ) -> list[str]:
        return [
            "claude",
            "--dangerously-skip-permissions",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--model",
            model,
            prompt,
        ]


class CodexBackend(Backend):
    name = "codex"

    def build_argv(
        self,
        prompt: str,
        model: str,
        reasoning: str,
        cwd: Path,
    ) -> list[str]:
        return [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-C",
            str(cwd),
            "-m",
            model,
            "-c",
            f"reasoning={reasoning}",
            prompt,
        ]


_BACKENDS: dict[str, Backend] = {
    "claude": ClaudeBackend(),
    "codex": CodexBackend(),
}


def get_backend(name: str) -> Backend:
    b = _BACKENDS.get(name)
    if b is None:
        raise ValueError(f"unknown backend: {name!r} (available: {list(_BACKENDS)})")
    return b
