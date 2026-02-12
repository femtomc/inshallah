from __future__ import annotations

import pytest

from loopfarm import cli


def _write_program(
    tmp_path,
    *,
    body: str,
) -> None:
    path = tmp_path / ".loopfarm" / "loopfarm.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _minimal_program_toml() -> str:
    return """
[program]
name = "impl"
project = "alpha"
steps = ["planning", "forward*2", "backward"]
termination_phase = "backward"
report_source_phase = "forward"
report_target_phases = ["backward"]

[program.phase.planning]
cli = "codex"
prompt = ".loopfarm/prompts/planning.md"
model = "gpt-5.2"
reasoning = "xhigh"

[program.phase.forward]
cli = "codex"
prompt = ".loopfarm/prompts/forward.md"
model = "gpt-5.3-codex"
reasoning = "high"
inject = ["phase_briefing"]

[program.phase.backward]
cli = "codex"
prompt = ".loopfarm/prompts/backward.md"
model = "gpt-5.2"
reasoning = "xhigh"
inject = ["forward_report"]
"""


def test_main_requires_program_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 2


def test_main_builds_cfg_from_program(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    captured = {}

    def fake_run_loop(cfg):
        captured["cfg"] = cfg
        return 0

    _write_program(tmp_path, body=_minimal_program_toml())
    monkeypatch.setattr(cli, "run_loop", fake_run_loop)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 0

    cfg = captured["cfg"]
    assert cfg.project == "alpha"
    assert cfg.loop_plan_once is True
    assert cfg.loop_steps == (("forward", 2), ("backward", 1))
    assert cfg.termination_phase == "backward"
    assert cfg.loop_report_source_phase == "forward"
    assert cfg.loop_report_target_phases == ("backward",)
    assert cfg.phase_cli_overrides == (
        ("planning", "codex"),
        ("forward", "codex"),
        ("backward", "codex"),
    )
    assert cfg.phase_prompt_overrides == (
        ("planning", ".loopfarm/prompts/planning.md"),
        ("forward", ".loopfarm/prompts/forward.md"),
        ("backward", ".loopfarm/prompts/backward.md"),
    )
    assert cfg.phase_injections == (
        ("forward", ("phase_briefing",)),
        ("backward", ("forward_report",)),
    )
    assert cfg.phase_model("forward") is not None
    assert cfg.phase_model("forward").model == "gpt-5.3-codex"  # type: ignore[union-attr]


def test_main_project_flag_overrides_program_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    captured = {}

    def fake_run_loop(cfg):
        captured["cfg"] = cfg
        return 0

    _write_program(tmp_path, body=_minimal_program_toml())
    monkeypatch.setattr(cli, "run_loop", fake_run_loop)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["--project", "override", "Implement feature"])

    assert raised.value.code == 0
    assert captured["cfg"].project == "override"


def test_main_rejects_program_name_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_program(tmp_path, body=_minimal_program_toml())
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["--program", "other", "Implement feature"])

    assert raised.value.code == 2


def test_main_rejects_missing_program_phase_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_program(
        tmp_path,
        body="""
[program]
name = "impl"
steps = ["planning", "forward", "backward"]
termination_phase = "backward"

[program.phase.planning]
cli = "codex"
prompt = "planning.md"
model = "gpt-5.2"

[program.phase.backward]
cli = "codex"
prompt = "backward.md"
model = "gpt-5.2"
""",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 2


def test_main_rejects_missing_prompt_for_phase(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_program(
        tmp_path,
        body="""
[program]
name = "impl"
steps = ["forward", "backward"]
termination_phase = "backward"

[program.phase.forward]
cli = "codex"
model = "gpt-5.3-codex"

[program.phase.backward]
cli = "codex"
prompt = "backward.md"
model = "gpt-5.2"
""",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 2


def test_main_rejects_missing_cli_for_phase(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_program(
        tmp_path,
        body="""
[program]
name = "impl"
steps = ["forward", "backward"]
termination_phase = "backward"

[program.phase.forward]
prompt = "forward.md"
model = "gpt-5.3-codex"

[program.phase.backward]
cli = "codex"
prompt = "backward.md"
model = "gpt-5.2"
""",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 2


def test_main_rejects_missing_model_for_non_kimi_phase(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_program(
        tmp_path,
        body="""
[program]
name = "impl"
steps = ["forward", "backward"]
termination_phase = "backward"

[program.phase.forward]
cli = "codex"
prompt = "forward.md"

[program.phase.backward]
cli = "codex"
prompt = "backward.md"
model = "gpt-5.2"
""",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 2


def test_main_allows_kimi_phase_without_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    captured = {}

    def fake_run_loop(cfg):
        captured["cfg"] = cfg
        return 0

    _write_program(
        tmp_path,
        body="""
[program]
name = "impl"
steps = ["forward", "backward"]
termination_phase = "backward"

[program.phase.forward]
cli = "kimi"
prompt = "forward.md"

[program.phase.backward]
cli = "codex"
prompt = "backward.md"
model = "gpt-5.2"
""",
    )
    monkeypatch.setattr(cli, "run_loop", fake_run_loop)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as raised:
        cli.main(["Implement feature"])

    assert raised.value.code == 0
    assert captured["cfg"].phase_model("forward") is None
