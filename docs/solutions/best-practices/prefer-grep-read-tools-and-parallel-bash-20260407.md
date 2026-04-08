---
module: agent-workflow
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: low
tags: [agent-tools, grep, read, parallelism, token-efficiency]
applies_when:
  - performing searches or reads in an agent session
  - multiple independent commands can run concurrently
  - optimizing token usage and latency
---

# Prefer Grep/Read tools over shell grep/cat; batch independent Bash calls

## Context

Shell `grep`, `cat`, `head`, `tail`, `find`, and `ls` work, but they route through the Bash tool — which imposes permission checks, shell init cost, and returns raw output into context. The dedicated Grep/Read/Glob tools are cheaper, clearer in the transcript, and already respect `.gitignore` and permission boundaries. Independent Bash calls issued sequentially also waste wall-clock time.

## Guidance

- **Content search** — use `Grep` (ripgrep under the hood), never `grep`/`rg` via Bash.
- **File reads** — use `Read` with an absolute path, never `cat`/`head`/`tail`.
- **File discovery** — use `Glob` for name patterns, never `find`/`ls`.
- **Edits** — use `Edit`/`Write`, never `sed`/`awk`/heredocs via Bash.
- **Parallelism** — when N Bash calls are independent (no data dependency between them), issue them in a single assistant turn as N parallel tool calls, not sequentially.

## Why This Matters

- Grep's `files_with_matches` mode returns paths only — orders of magnitude cheaper than `grep -rn` dumped into context.
- Read's line-numbered output is what Edit requires as a precondition; using `cat` forces a second Read anyway.
- Parallel tool calls in a single turn cut latency roughly linearly — 4 independent 2s commands become one 2s wall-clock slot.
- Transcripts stay auditable: each tool call has a typed schema that tooling (hooks, review bots) can analyze; raw Bash output is opaque.

## When to Apply

- Every search, every read, every glob — unless the dedicated tool genuinely cannot express the query (rare; document why if you fall back).
- Any turn where you're about to issue `git status` + `git diff` + `git log` sequentially — batch them.
- Any turn where you're checking multiple independent files (read 3 configs, run 2 test suites) — batch them.

## Examples

```text
# Bad — sequential, 3 turns, 3 round-trips
turn 1: Bash("git status")
turn 2: Bash("git diff")
turn 3: Bash("git log -5")

# Good — one turn, parallel, 1 round-trip
turn 1: Bash("git status"), Bash("git diff"), Bash("git log -5")
```

```text
# Bad
Bash("grep -rn 'fn parse_session' middens/src")

# Good
Grep(pattern="fn parse_session", path="middens/src", output_mode="content", -n=true)
```
