# Prompts

Prompt templates for `loopfarm` automated loops.

## Quick Usage

```bash
# Default implementation loop
loopfarm "Implement an HTTP retry strategy"

# Research/planning loop
loopfarm --mode research "Survey queueing architectures"

# Custom implementation loop shape
loopfarm --mode implementation --phase-plan "planning,forward*5,documentation,architecture,backward" "Improve ingestion latency"
```

## CLI Families

`loopfarm` has one primary CLI with subcommands:

```bash
loopfarm <prompt...>           # run loop
loopfarm issue ...             # issue tracker
loopfarm forum ...             # forum/message store
loopfarm monitor ...           # monitoring server/frontend
```

## Modes

### Implementation mode (`--mode implementation`, default)

State machine:

```text
planning_once -> (forward^N -> documentation -> architecture -> backward_decision)^K
```

- `planning` prepares issue graph and acceptance criteria.
- `forward` executes one concrete leaf issue per pass.
- `documentation` updates docs/prose to match implementation changes.
- `architecture` records modularity/performance findings as issue follow-ups.
- `backward` is the sole termination gate.

### Research mode (`--mode research`)

State machine:

```text
planning_once -> (research^N -> curation -> backward_decision)^K
```

- `planning` defines scope/hypotheses and artifact structure.
- `research` gathers evidence from papers, production systems, and source code.
- `curation` organizes findings into implementation-ready issue graph.
- `backward` decides readiness to hand off to implementation mode.

### Writing mode (`--mode writing`)

Uses implementation templates with extra writing-specific guardrails from
`prompts/writing.md`.

## Template Resolution

For phase `<phase>`, loopfarm resolves templates in order:

1. `prompts/<mode>/<phase>.md`
2. `prompts/implementation/<phase>.md`
3. `prompts/<phase>.md` (legacy fallback)

Runtime placeholders:

- `{{PROMPT}}`
- `{{SESSION}}`
- `{{PROJECT}}`
- `{{DYNAMIC_CONTEXT}}`
- `{{PHASE_BRIEFING}}`
- `{{FORWARD_REPORT}}`

Optional split placeholders for operator context:

- `{{SESSION_CONTEXT}}`
- `{{USER_CONTEXT}}`

## Data Contracts

Loop state is written to `loopfarm forum` topics.

Common topics:

- `loopfarm:session:<session>`
- `loopfarm:control:<session>`
- `loopfarm:context:<session>`
- `loopfarm:briefing:<session>`
- `loopfarm:forward:<session>`
- `loopfarm:status:<session>`

Issue coordination uses `loopfarm issue`.

## Models and Backends

Default backend/model behavior:

- Forward: Codex (`gpt-5.3-codex`, `reasoning=xhigh`)
- Planning/review/research/curation: Codex (`gpt-5.2`, `reasoning=xhigh`)
- Documentation: Gemini (`gemini-3-pro-preview`)
- Architecture: Codex (`gpt-5.2`, `reasoning=xhigh`)

Override with `LOOPFARM_*` env vars, including:

- `LOOPFARM_CODE_MODEL`, `LOOPFARM_PLAN_MODEL`, `LOOPFARM_REVIEW_MODEL`
- `LOOPFARM_ARCHITECTURE_MODEL`, `LOOPFARM_DOCUMENTATION_MODEL`
- `LOOPFARM_CODE_REASONING`, `LOOPFARM_PLAN_REASONING`, `LOOPFARM_REVIEW_REASONING`, `LOOPFARM_ARCHITECTURE_REASONING`
- `LOOPFARM_IMPLEMENTATION_LOOP`, `LOOPFARM_RESEARCH_LOOP`
