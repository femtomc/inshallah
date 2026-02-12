# Program Step Grammar

`[program].steps` defines loop structure.

## Grammar

```ebnf
steps       := token ("," token)* | [token, ...]
token       := phase ["*" integer]
phase       := "planning" | "forward" | "research" | "curation" | "documentation" | "architecture" | "backward"
integer     := [1-9][0-9]*
```

## Rules

- `planning` may appear only as the first step.
- `planning` cannot be repeated.
- At least one non-planning phase is required.
- `termination_phase` must exist in the non-planning loop steps.

## Examples

Implementation:

```text
planning,forward*5,documentation,architecture,backward
```

Research:

```text
planning,research*3,curation,backward
```
