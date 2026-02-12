# Implementation Program State Machine

Implementation is defined by the configured program, not hardcoded modes.

## Shape

```text
planning_once -> (forward^N -> documentation -> architecture -> backward)^K
```

`planning_once` runs only when `planning` is the first step in `[program].steps`.

## Termination

- `termination_phase` in config is the only completion gate.
- The runner completes only when that phase writes `decision=COMPLETE` to `loopfarm:status:<session>`.

## Forward Report Flow

When configured:

- `[program].report_source_phase` captures source summaries.
- `[program].report_target_phases` receives the generated report.
- Injection into prompts is explicit per phase with `inject = ["forward_report"]`.
