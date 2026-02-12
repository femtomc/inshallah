# Incremental Backward Protocol

Backward passes should be incremental: re-audit only what changed since the
last audit marker.

## Forum Topics

| Topic | Purpose |
| --- | --- |
| `backward:state:<project>` | last audited commit + scope |
| `backward:findings:<project>` | structured findings from this audit |
| `backward:literature:<project>` | cached external research notes |
| `loopfarm:forward:<session>` | forward pass report for current session |

## Suggested Message Shapes

State:

```json
{
  "commit": "abc123",
  "timestamp": "2026-01-17T12:00:00Z",
  "categories_audited": ["api", "storage", "runtime"],
  "files_audited": ["src/foo.py", "src/bar.py"]
}
```

Findings:

```json
{
  "category": "storage",
  "commit": "abc123",
  "findings": [
    {
      "file": "src/storage.py",
      "line": 42,
      "issue": "Inefficient full-table scan",
      "severity": "high"
    }
  ],
  "issues_filed": ["loopfarm-abc123"]
}
```

Literature cache:

```json
{
  "query": "high-throughput task queue architecture",
  "query_hash": "a1b2c3",
  "timestamp": "2026-01-17T12:00:00Z",
  "ttl_days": 7,
  "results": [
    {"title": "Paper title", "year": 2024, "relevance": "high"}
  ],
  "actions_taken": ["Filed issue loopfarm-xyz"]
}
```

## Invalidations

Re-audit when any of these hold:

1. Relevant files changed since last audited commit.
2. Category has never been audited.
3. Operator requested a full refresh.

Refresh literature when any of these hold:

1. TTL expired.
2. Related code changed.
3. Query was never run.
4. Operator requested refresh.

## Recommended Backward Flow

1. Load last state:

```bash
loopfarm forum read backward:state:<project> --limit 1
```

2. Diff from last commit and define audit scope:

```bash
git log --oneline <last-commit>..HEAD
git diff --name-only <last-commit>..HEAD
```

3. Run scoped audit only on invalidated categories.
4. Run issue triage with `loopfarm issue`.
5. Post updated state/findings:

```bash
loopfarm forum post backward:state:<project> -m '<json>'
loopfarm forum post backward:findings:<project> -m '<json>'
```
