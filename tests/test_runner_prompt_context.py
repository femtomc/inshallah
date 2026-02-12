from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from loopfarm.runner import (
    CodexPhaseModel,
    LoopfarmConfig,
    LoopfarmRunner,
    StopRequested,
)


def _write_prompts(
    tmp_path: Path,
    *,
    include_placeholder: bool = True,
    include_required_summary: bool = True,
) -> None:
    prompts_root = tmp_path / "loopfarm" / "prompts" / "implementation"
    prompts_root.mkdir(parents=True)
    for phase in ("planning", "forward", "backward"):
        header = f"{phase.upper()} {{PROMPT}} {{SESSION}} {{PROJECT}}"
        header = (
            header.replace("{PROMPT}", "{{PROMPT}}")
            .replace("{SESSION}", "{{SESSION}}")
            .replace("{PROJECT}", "{{PROJECT}}")
        )
        lines = [header, ""]
        if include_placeholder:
            lines.append("{{DYNAMIC_CONTEXT}}")
            lines.append("")
        lines.append("## Workflow")
        lines.append("Do the thing.")
        if include_required_summary:
            lines.extend(["", "## Required Phase Summary", "Summary goes here.", ""])
        (prompts_root / f"{phase}.md").write_text("\n".join(lines), encoding="utf-8")


def _write_prompt_variants(
    tmp_path: Path,
    *,
    marker: str,
) -> None:
    prompts_root = tmp_path / "loopfarm" / "prompts" / "implementation"
    prompts_root.mkdir(parents=True, exist_ok=True)
    for phase in ("planning", "forward", "backward"):
        header = f"{marker} {phase.upper()} {{PROMPT}} {{SESSION}} {{PROJECT}}"
        header = (
            header.replace("{PROMPT}", "{{PROMPT}}")
            .replace("{SESSION}", "{{SESSION}}")
            .replace("{PROJECT}", "{{PROJECT}}")
        )
        lines = [header, "", "## Required Phase Summary", "Summary goes here."]
        (prompts_root / f"{phase}.md").write_text("\n".join(lines), encoding="utf-8")


def _cfg(tmp_path: Path) -> LoopfarmConfig:
    model = CodexPhaseModel(model="test", reasoning="fast")
    return LoopfarmConfig(
        repo_root=tmp_path,
        cli="claude",
        model_override=None,
        skip_plan=True,
        project="test",
        prompt="Example prompt",
        code_model=model,
        plan_model=model,
        review_model=model,
    )


def test_build_phase_prompt_injects_session_context(tmp_path: Path) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_context_override = "Pinned guidance"

    prompt = runner._build_phase_prompt("sess", "planning")

    assert "PLANNING Example prompt sess test" in prompt
    assert "## Session Context" in prompt
    assert "Pinned guidance" in prompt
    assert "## Operator Context" not in prompt
    assert "## Required Phase Summary" in prompt
    assert prompt.index("## Session Context") < prompt.index("## Required Phase Summary")


def test_session_context_persists_across_phases(tmp_path: Path) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_context_override = "Carry over"

    prompt_one = runner._build_phase_prompt("sess", "planning")
    prompt_two = runner._build_phase_prompt("sess", "forward")

    assert "Carry over" in prompt_one
    assert "Carry over" in prompt_two


def test_build_phase_prompt_without_context_returns_base(tmp_path: Path) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))

    prompt = runner._build_phase_prompt("sess", "forward")

    assert "FORWARD Example prompt sess test" in prompt
    assert "## Session Context" not in prompt
    assert "## Operator Context" not in prompt
    assert "{{DYNAMIC_CONTEXT}}" not in prompt


def test_prompt_injects_context_before_summary_without_placeholder(
    tmp_path: Path,
) -> None:
    _write_prompts(tmp_path, include_placeholder=False)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_context_override = "Pinned guidance"

    prompt = runner._build_phase_prompt("sess", "forward")

    assert "## Session Context" in prompt
    assert prompt.index("## Session Context") < prompt.index("## Required Phase Summary")


def test_control_checkpoint_pause_then_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_id = "sess"

    states = [
        {
            "timestamp": "2026-02-12T10:00:00Z",
            "command": "pause",
            "author": "op",
        },
        {
            "timestamp": "2026-02-12T10:00:01Z",
            "command": "resume",
            "author": "op",
        },
    ]

    def next_state(_: str):
        if states:
            return states.pop(0)
        return None

    monkeypatch.setattr(runner, "_read_control_state", next_state)
    monkeypatch.setattr(runner, "_sleep", lambda _seconds: None)

    runner._control_checkpoint(session_id="sess", phase="forward", iteration=1)

    assert runner.paused is False
    meta = runner.session_store.get_session_meta("sess") or {}
    assert meta.get("status") == "running"


def test_control_checkpoint_stop_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))

    state = {
        "timestamp": "2026-02-12T10:00:00Z",
        "command": "stop",
        "author": "op",
    }

    monkeypatch.setattr(runner, "_read_control_state", lambda _sid: state)

    with pytest.raises(StopRequested):
        runner._control_checkpoint(session_id="sess", phase="forward", iteration=1)

    assert runner.session_status == "stopped"


def test_control_state_context_set_and_clear(tmp_path: Path) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_id = "sess"

    runner._apply_control_state(
        state={
            "timestamp": "2026-02-12T10:00:00Z",
            "command": "context_set",
            "content": "Use this context",
            "author": "op",
        },
        session_id="sess",
        phase="planning",
        iteration=0,
    )

    assert runner.session_context_override == "Use this context"
    meta = runner.session_store.get_session_meta("sess") or {}
    assert meta.get("session_context") == "Use this context"

    runner._apply_control_state(
        state={
            "timestamp": "2026-02-12T10:00:01Z",
            "command": "context_clear",
            "author": "op",
        },
        session_id="sess",
        phase="planning",
        iteration=0,
    )

    assert runner.session_context_override == ""
    meta = runner.session_store.get_session_meta("sess") or {}
    assert meta.get("session_context") == ""


def test_load_session_context_override_from_store(tmp_path: Path) -> None:
    _write_prompts(tmp_path)
    runner = LoopfarmRunner(_cfg(tmp_path))
    runner.session_store.update_session_meta(
        "sess",
        {"session_context": "Pinned guidance"},
        author="tester",
    )

    runner._load_session_context_override("sess")

    assert runner.session_context_override == "Pinned guidance"


def test_prompt_paths_use_shared_set_for_all_backends(tmp_path: Path) -> None:
    _write_prompt_variants(tmp_path, marker="BASE")

    cfg = replace(_cfg(tmp_path), forward_cli="codex")
    runner = LoopfarmRunner(cfg)

    planning_prompt = runner._render_phase_prompt("sess", "planning")
    forward_prompt = runner._render_phase_prompt("sess", "forward")
    backward_prompt = runner._render_phase_prompt("sess", "backward")

    assert planning_prompt.startswith("BASE PLANNING")
    assert backward_prompt.startswith("BASE BACKWARD")
    assert forward_prompt.startswith("BASE FORWARD")


def test_prompt_path_precedence_mode_then_implementation_then_legacy(
    tmp_path: Path,
) -> None:
    prompts_root = tmp_path / "loopfarm" / "prompts"
    impl_root = prompts_root / "implementation"
    research_root = prompts_root / "research"
    impl_root.mkdir(parents=True, exist_ok=True)
    research_root.mkdir(parents=True, exist_ok=True)

    (prompts_root / "forward.md").write_text(
        "LEGACY FORWARD {{PROMPT}}\n## Required Phase Summary\nSummary\n",
        encoding="utf-8",
    )
    (impl_root / "forward.md").write_text(
        "IMPLEMENTATION FORWARD {{PROMPT}}\n## Required Phase Summary\nSummary\n",
        encoding="utf-8",
    )
    (research_root / "forward.md").write_text(
        "RESEARCH FORWARD {{PROMPT}}\n## Required Phase Summary\nSummary\n",
        encoding="utf-8",
    )

    research_runner = LoopfarmRunner(replace(_cfg(tmp_path), mode="research"))
    writing_runner = LoopfarmRunner(replace(_cfg(tmp_path), mode="writing"))
    no_mode_runner = LoopfarmRunner(_cfg(tmp_path))

    assert research_runner._render_phase_prompt("sess", "forward").startswith(
        "RESEARCH FORWARD"
    )
    assert writing_runner._render_phase_prompt("sess", "forward").startswith(
        "IMPLEMENTATION FORWARD"
    )
    assert no_mode_runner._render_phase_prompt("sess", "forward").startswith(
        "IMPLEMENTATION FORWARD"
    )


def test_prompt_path_supports_legacy_root_templates(tmp_path: Path) -> None:
    prompts_root = tmp_path / "loopfarm" / "prompts"
    prompts_root.mkdir(parents=True, exist_ok=True)
    (prompts_root / "forward.md").write_text(
        "LEGACY FORWARD {{PROMPT}}\n## Required Phase Summary\nSummary\n",
        encoding="utf-8",
    )

    runner = LoopfarmRunner(replace(_cfg(tmp_path), mode="implementation"))

    assert runner._render_phase_prompt("sess", "forward").startswith("LEGACY FORWARD")


def test_writing_mode_injects_guidance_into_shared_prompts(
    tmp_path: Path,
) -> None:
    _write_prompt_variants(tmp_path, marker="BASE")

    cfg = replace(_cfg(tmp_path), forward_cli="codex", mode="writing")
    runner = LoopfarmRunner(cfg)

    planning_prompt = runner._build_phase_prompt("sess", "planning")
    forward_prompt = runner._build_phase_prompt("sess", "forward")
    backward_prompt = runner._build_phase_prompt("sess", "backward")

    assert planning_prompt.startswith("BASE PLANNING")
    assert forward_prompt.startswith("BASE FORWARD")
    assert backward_prompt.startswith("BASE BACKWARD")
    assert "## Writing Mode" in planning_prompt
    assert "## Writing Mode" in forward_prompt
    assert "## Writing Mode" in backward_prompt
