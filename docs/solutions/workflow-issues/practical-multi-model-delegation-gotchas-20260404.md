---
title: "Practical multi-model delegation gotchas"
module: tooling
date: 2026-04-04
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Delegating work to Codex, Gemini, or OpenCode CLI tools"
  - "Running adversarial red/green across multiple models"
  - "Parallel fan-out to competing implementations"
tags:
  - delegation
  - codex
  - gemini
  - opencode
  - multi-model
  - adversarial
---

# Practical Multi-Model Delegation Gotchas

## Context

Learned from 3 adversarial development sessions on the middens project, delegating across Claude, Codex (GPT-5.4), Gemini 3.1 Pro, GLM 5.1, Minimax M2.7, and Kimi K2.5.

## Guidance

### Model selection for green team roles

| Model | Strengths | Weaknesses | Best for |
|-------|-----------|------------|----------|
| Codex (GPT-5.4) | Fast, reliable file writes, good reasoning | Expensive | Red team tests, targeted fixes |
| Gemini 3.1 Pro | Good at spec writing, reviewing, multi-step tasks | Rate limits (429), sometimes verbose | Spec author, reviewer, red team |
| GLM 5.1 (OpenCode) | Correct architecture, proper I/O handling | Slow (5-10 min), minimal output | Green team implementation |
| Minimax M2.7 (OpenCode) | Produces more code, faster than GLM | Architectural bugs (deadlocked timeout) | Secondary green team candidate |
| Kimi K2.5 (OpenCode) | Good code synthesis, works with tools via OpenCode | Needs `--format json` + correct model ID | Green team coder (validated in A²D) |

### Invocation gotchas

**Codex:**
- Always `timeout: 600000` on Bash tool calls
- Use `-o output.md` for output capture, never pipe through `tail`
- `--full-auto` for file writes, `-C <dir>` for working directory

**Gemini:**
- `-y -s false` (yolo + no sandbox) for file writes
- Hits 429 rate limits on heavy sessions — retry or wait
- Good at self-review when asked explicitly

**OpenCode:**
- Background dispatch: `opencode run --model provider/model --dir <dir> "prompt" > log.log 2>&1 &`
- Can be very slow (5-15 min for complex tasks)
- No sandbox — writes directly to filesystem
- Kimi K2.5: use `--format json` to get NDJSON output — without it, ANSI escape codes corrupt code extraction
- Kimi model ID is `kimi-for-coding/k2p5` (not `kimi/kimi-k2.5` — the old ID caused silent failures)
- Kimi tool use works through OpenCode's tool layer, not Kimi's raw API — validated in A²D project (skunkworks/a2d)

### Parallel worktrees fill disk

Three parallel `cargo build` worktrees can consume 5+ GB each. On a 140 GB disk, this can cause `ENOSPC` (errno 28) linker failures. Clean up worktrees immediately after comparing implementations:

```bash
git worktree remove /tmp/worktree-name --force
rm -rf /tmp/worktree-name
```

### NLSpec process order

1. Write the NLSpec — give the author the format references (jhugman.com/posts/on-nlspecs/, github.com/strongdm/attractor)
2. Review the NLSpec — is the How section detailed enough? Are error paths specified?
3. THEN derive tests from the DoD

Never combine spec writing + test writing in one prompt. The spec needs review before tests are derived from it.

### GitHub API limitations

- Review comments created via `gh api repos/.../pulls/.../comments/.../replies` cannot be PATCHed — get the reply right the first time
- `gh pr merge --squash` does not auto-delete the remote branch — delete manually
- `git push --force --all` pushes to ALL branches including merged ones — use `git push --force origin main feat/branch` to target specific branches

### Adversarial contract amendments

When the green team's API deviates from the NLSpec:
1. **Pause** — don't adapt either side
2. **Evaluate** — is it an improvement, a spec gap, or an error?
3. If improvement: amend the NLSpec, red team rewrites tests
4. If error: route PASS/FAIL back to green

Never tell the red team to rewrite tests to match an unauthorized deviation. That inverts the authority chain.

## Why This Matters

Multi-model delegation is powerful but the failure modes are non-obvious. A deadlocked timeout implementation (Minimax), a disk-full linker failure (worktrees), and an inverted authority chain (contract amendment) all happened in a single session. Each one wasted 10-30 minutes of compute.

**Update (2026-04-04):** The original Kimi "tool-calling error" finding was incorrect. The A²D project (skunkworks/a2d-autopoietic-autocatalysis-deutero) demonstrated that Kimi K2.5 successfully uses tools through OpenCode when invoked with `--format json` and the correct model ID (`kimi-for-coding/k2p5`). The original failure was caused by wrong model IDs and ANSI escape code corruption in unparsed output.

## Related

- [Adversarial methodology](../best-practices/adversarial-red-green-development-methodology.md) (in foundry)
- [Orchestrator reconciliation breaks provenance](../../foundry/docs/solutions/workflow-issues/orchestrator-reconciliation-breaks-provenance-20260401.md) (in foundry)
- [Codex CLI skill](/Users/thomas/.claude/skills/codex-cli/SKILL.md) — timeout gotcha documented in Gotchas section
