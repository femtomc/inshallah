"""CLI entry point for loopfarm."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from . import __version__
from .dag import DagRunner
from .store import ForumStore, IssueStore

_SUBCOMMANDS = {"init"}


def _find_repo_root() -> Path:
    """Walk up to find .git directory."""
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()


def _run_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loopfarm", add_help=False)
    p.add_argument("prompt", nargs="*")
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--cli", default="codex", choices=["codex", "claude"])
    p.add_argument("--model", default="o3")
    p.add_argument("--reasoning", default="high")
    p.add_argument("--prompt-path", default=None)
    p.add_argument("--json", action="store_true")
    return p


def cmd_init(console: Console) -> int:
    root = _find_repo_root()
    lf = root / ".loopfarm"
    lf.mkdir(exist_ok=True)
    (lf / "issues.jsonl").touch()
    (lf / "forum.jsonl").touch()

    orch = lf / "orchestrator.md"
    if not orch.exists():
        orch.write_text(
            "---\n"
            "cli: codex\n"
            "model: o3\n"
            "reasoning: high\n"
            "---\n\n"
            "{{PROMPT}}\n\n"
            "{{DYNAMIC_CONTEXT}}\n\n"
            "You are an orchestrator agent. Execute the task described above.\n"
            "When done, close the issue using the loopfarm issue store.\n"
        )

    (lf / "logs").mkdir(exist_ok=True)
    console.print(f"[green]Initialized .loopfarm/ in {root}[/green]")
    return 0


def cmd_run(args: argparse.Namespace, console: Console) -> int:
    root = _find_repo_root()
    store = IssueStore.from_workdir(root)
    forum = ForumStore.from_workdir(root)

    prompt_text = " ".join(args.prompt)
    if not prompt_text:
        console.print("[red]No prompt provided.[/red]")
        return 1

    root_issue = store.create(
        prompt_text,
        tags=["node:agent", "node:root"],
        execution_spec={
            "role": "orchestrator",
            "prompt_path": args.prompt_path or "",
            "cli": args.cli,
            "model": args.model,
            "reasoning": args.reasoning,
        },
    )
    console.print(
        f"[bold]Root issue:[/bold] {root_issue['id']} — {prompt_text[:80]}"
    )

    runner = DagRunner(
        store,
        forum,
        root,
        default_cli=args.cli,
        default_model=args.model,
        default_reasoning=args.reasoning,
        console=console,
    )
    result = runner.run(root_issue["id"], max_steps=args.max_steps)

    if args.json:
        json.dump(
            {
                "status": result.status,
                "steps": result.steps,
                "error": result.error,
                "root_id": root_issue["id"],
            },
            sys.stdout,
            indent=2,
        )
        print()

    return 0 if result.status == "root_final" else 1


def main(argv: list[str] | None = None) -> None:
    raw = argv if argv is not None else sys.argv[1:]
    console = Console()

    # Handle --version and --help at top level
    if "--version" in raw:
        print(f"loopfarm {__version__}")
        sys.exit(0)
    if not raw or raw == ["--help"] or raw == ["-h"]:
        console.print(
            f"[bold]loopfarm[/bold] {__version__} — "
            "DAG-based loop runner for agentic workflows\n"
        )
        console.print("Usage:")
        console.print("  loopfarm init                  Scaffold .loopfarm/")
        console.print("  loopfarm <prompt>              Create root issue and run DAG")
        console.print("  loopfarm <prompt> [options]    Run with options\n")
        console.print("Options:")
        console.print("  --max-steps N       Step budget (default: 20)")
        console.print("  --cli codex|claude  Default backend (default: codex)")
        console.print("  --model MODEL       Default model (default: o3)")
        console.print("  --reasoning LEVEL   Reasoning level (default: high)")
        console.print("  --prompt-path PATH  Prompt template path")
        console.print("  --json              JSON output")
        console.print("  --version           Show version")
        sys.exit(0)

    # Subcommand dispatch
    if raw[0] == "init":
        sys.exit(cmd_init(console))

    # Everything else is a run command
    args = _run_parser().parse_args(raw)
    sys.exit(cmd_run(args, console))


if __name__ == "__main__":
    main()
