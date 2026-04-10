---
title: "Parallel agent dispatches to shared working tree cause edit races"
date: "2026-04-10"
category: workflow-issues
module: agent-orchestration
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - Dispatching multiple coding agents (OpenCode, Codex, Gemini CLI) in parallel
  - Orchestrator needs to edit files between or during parallel agent runs
  - Using CLI-based agents that lack built-in workspace isolation
tags:
  - parallel-dispatch
  - race-condition
  - working-tree
  - opencode
  - agent-isolation
  - worktree
---

# Parallel Agent Dispatches to Shared Working Tree Cause Edit Races

## Context

During a middens CLI feature implementation, three GLM 5.1 agents were dispatched simultaneously via `opencode run --model zai-coding-plan/glm-5.1` to implement Groups B, C, and E of a CLI feature. All three shared the same git working tree — no worktrees, no isolation.

Between dispatches, the orchestrator (Claude Opus) needed to fix a PII blocklist issue in `src/storage/mod.rs`. The `Edit` tool reported success, but a `Read` immediately after showed the old content. The file had been silently reverted.

**Root cause:** OpenCode processes read files at dispatch time and write modified versions later. If the orchestrator edits a file between read and write, the OpenCode write overwrites the orchestrator's change. The orchestrator's edit is silently lost — no error, no conflict, no warning.

**Immediate fix:** `pkill -f opencode` to kill lingering processes, then re-apply the edit.

## Guidance

### Use git worktrees for parallel CLI agent dispatches

Every parallel agent dispatch should get its own worktree. This is the only reliable isolation mechanism for CLI-based agents that read-modify-write files independently.

```bash
# Create isolated worktrees before dispatch
git worktree add /tmp/wt-group-b HEAD
git worktree add /tmp/wt-group-c HEAD
git worktree add /tmp/wt-group-e HEAD

# Dispatch each agent to its own worktree
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-group-b "prompt B" > /tmp/log-b.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-group-c "prompt C" > /tmp/log-c.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-group-e "prompt E" > /tmp/log-e.log 2>&1 &

# After completion, cherry-pick or merge results back
# Then clean up
git worktree remove /tmp/wt-group-b --force
git worktree remove /tmp/wt-group-c --force
git worktree remove /tmp/wt-group-e --force
```

### For Claude subagents, use the built-in isolation parameter

The Claude Code Agent tool has `isolation: "worktree"` which handles this automatically. But this only works for Claude subagents — external CLI tools (OpenCode, Codex, Gemini CLI) need manual worktree setup.

### If worktrees are impractical, serialize dispatches

When disk space is tight (three `cargo build` worktrees can consume 15+ GB) or the task is small enough, dispatch sequentially. Slower but safe.

### Commit orchestrator fixes before the next wave

If you must use a shared tree: stage orchestrator fixes as commits before dispatching the next wave. This way all agents start from the committed state, and `git diff` will show what each agent changed relative to the orchestrator's fix.

## Why This Matters

The failure mode is **silent data loss**. The orchestrator's edit succeeds from its perspective — the `Edit` tool returns success, the diff looks correct. But moments later, a background agent overwrites the file with a stale version. There is no error, no merge conflict, no notification. The only symptom is that the fix "didn't stick," which looks like a tool bug rather than a race condition.

In the incident that surfaced this, the PII blocklist fix was security-relevant. A silently reverted security fix is worse than no fix at all, because the orchestrator proceeds as if the fix is in place.

## When to Apply

- **Always** when dispatching 2+ CLI agents (OpenCode, Codex, Gemini) that will write to overlapping files
- **Always** when the orchestrator plans to edit files while agents are still running
- **Especially** when the shared files are in hot paths (`src/`, `Cargo.toml`, shared modules) that multiple agents are likely to touch
- **Not needed** for read-only dispatches (e.g., review or analysis prompts that only produce stdout)

## Examples

### Bad: shared tree, parallel dispatch

```bash
# All three write to the same tree — race condition guaranteed
opencode run --model zai-coding-plan/glm-5.1 "implement group B" > /tmp/b.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 "implement group C" > /tmp/c.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 "implement group E" > /tmp/e.log 2>&1 &
# Orchestrator edits src/storage/mod.rs... silently reverted by agent finishing later
```

### Good: worktree-isolated parallel dispatch

```bash
git worktree add /tmp/wt-b HEAD
git worktree add /tmp/wt-c HEAD
git worktree add /tmp/wt-e HEAD

opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-b "implement group B" > /tmp/b.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-c "implement group C" > /tmp/c.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-e "implement group E" > /tmp/e.log 2>&1 &

# Orchestrator safely edits main tree while agents work in isolation
# Merge results back via cherry-pick after all agents complete
```

### Good: commit-then-dispatch pattern (shared tree, sequential waves)

```bash
# Wave 1: dispatch group B
opencode run --model zai-coding-plan/glm-5.1 "implement group B" > /tmp/b.log 2>&1
# Wait for completion, review, commit

# Orchestrator fix
# Edit src/storage/mod.rs...
git add src/storage/mod.rs && git commit -m "fix: PII blocklist edge case"

# Wave 2: dispatch groups C and E (they start from the committed fix)
git worktree add /tmp/wt-c HEAD
git worktree add /tmp/wt-e HEAD
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-c "implement group C" > /tmp/c.log 2>&1 &
opencode run --model zai-coding-plan/glm-5.1 --dir /tmp/wt-e "implement group E" > /tmp/e.log 2>&1 &
```
