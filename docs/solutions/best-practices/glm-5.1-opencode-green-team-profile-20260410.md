---
title: "GLM 5.1 via OpenCode: slow but compiles, scope-creeps, runs rustfmt on everything"
date: "2026-04-10"
category: developer-experience
module: agent-orchestration
problem_type: developer_experience
component: tooling
severity: low
applies_when:
  - Using GLM 5.1 via OpenCode for code generation tasks
  - Evaluating model options for green team adversarial dispatches
  - Running overnight or background coding agent tasks where speed is not critical
tags:
  - glm
  - opencode
  - model-evaluation
  - green-team
  - code-generation
  - scope-creep
  - rustfmt
---

# GLM 5.1 via OpenCode: behavioral profile as a green team coding agent

## Context

GLM 5.1 (`zai-coding-plan/glm-5.1`) was used as the green team implementation agent for all 6 work groups of the middens CLI triad (storage, view, analyze, export, interpret, wiring). Dispatched via OpenCode in background mode. The choice was curiosity-driven ("I'm curious"), not a best-tool-for-the-job selection — which makes the results a useful baseline for future model evaluation.

The dispatch covered ~6 independent Rust implementation tasks ranging from 200 to 757 lines, each with explicit scope boundaries and file-level read/write permissions.

## Guidance

### Speed: plan for 5-15 minutes per dispatch

GLM 5.1 is the slowest of the available coding models. Kimi K2.5 is faster, Codex runs comparable tasks in ~90s. GLM is fine for background or overnight fan-out but unusable for interactive iteration loops where you need results in under a minute.

### Code quality: surprisingly good on first compile

4 of 6 work groups compiled on the first try. Group A (storage layer, 757 lines) was the standout — correct polars 0.46 usage, PII validation, manifest round-trips, 11 unit tests covering edge cases (blocklist, type mismatches, null handling, field ordering). Dependency choices were reasonable (polars over raw arrow2, tempfile for tests).

### Scope creep: expect it, plan for it

GLM touched files outside its assigned scope in every single dispatch. Group A was told "DO NOT touch `src/pipeline.rs` or `src/output/`" and modified both, plus all 6 technique files and `bridge/technique.rs`. The modifications were mostly mechanical — adding `column_types: None` to existing `DataTable` constructors for backwards compat — but they inflated diffs and created merge conflicts across parallel work groups.

### Rustfmt on everything: baked-in behavior

GLM ran `rustfmt` on every file it touched, including files it was told not to modify. This reformatted the `RISK_TOKENS` array from compact to one-per-line, reordered imports, and changed line wrapping across files outside scope. Arguably good practice in isolation; in a multi-agent parallel workflow it creates noise and merge pain.

### Instruction following: positive > negative

GLM reliably followed positive instructions ("read these files first", "document your rationale in a comment"). It reliably ignored negative instructions ("DO NOT touch pipeline.rs"). If your workflow depends on strict file-level isolation, GLM will violate it. Plan for a cleanup pass or use a model with better constraint adherence.

## Why This Matters

- Model selection for adversarial green team work is a real trade-off. GLM produces good code but creates operational overhead from scope violations. If you have 6 parallel groups writing to the same codebase, scope creep from any one group creates merge conflicts for all the others.
- The "runs rustfmt everywhere" behavior is invisible until you diff — it looks like the model rewrote half the codebase when it actually changed 3 lines of logic.
- Knowing that positive instructions stick better than negative ones lets you restructure prompts: instead of "DO NOT touch X", give GLM a working directory or explicit file list and omit X entirely.

## When to Apply

- **Use GLM 5.1 for**: background overnight dispatches where you want a second opinion on implementation, tasks with no shared-file constraints, self-contained modules with clear boundaries.
- **Avoid GLM 5.1 for**: interactive iteration (too slow), parallel multi-agent work on a shared worktree (scope creep causes merge conflicts), tasks where formatting stability matters (rustfmt noise).
- **Always**: run `git diff --stat` after a GLM dispatch to identify out-of-scope file touches before merging.

## Examples

### Dispatch pattern that worked

```bash
opencode run --model zai-coding-plan/glm-5.1 --format json "$(cat <<'PROMPT'
DIRECT TASK — no skills, no meta-workflows. Implement Group A of the CLI triad NLSpec directly.

You are a green-team implementation agent. Your job is to write correct, compiling Rust code.

READ THESE FIRST:
1. middens/src/storage/mod.rs (current state)
2. docs/nlspecs/middens-cli-triad.md sections 1-3 only

IMPLEMENT:
1. StorageManager with Parquet backend via polars 0.46
2. PII validation layer with RISK_TOKENS blocklist
3. Unit tests for round-trip, blocklist, type coercion

DO NOT: touch src/pipeline.rs or src/output/
DO NOT: read section 4 of the NLSpec (red team territory)
DO: run cargo check before declaring done
DO: document your dependency rationale in a top-of-file comment

FAIL EARLY, FAIL FAST, FAIL CLEARLY.
PROMPT
)" > /tmp/glm-group-a.log 2>&1 &
```

### Post-dispatch cleanup

```bash
# Check what GLM actually touched (expect surprises)
git diff --stat

# Revert out-of-scope formatting changes
git checkout -- src/pipeline.rs src/output/ src/techniques/

# Keep only the files GLM was supposed to write
git add middens/src/storage/
```

### Parse GLM output from NDJSON log

```bash
jq -r 'select(.type=="text") | .part.text' /tmp/glm-group-a.log
```
