---
title: "Reply-to-every-comment discipline and declining bot false positives"
module: tooling
date: 2026-04-07
problem_type: best_practice
component: development_workflow
applies_when:
  - "Automated reviewers (Codex, Copilot, Gemini, CodeRabbit) post findings on a PR"
  - "Some findings are wrong or not worth acting on"
  - "A human reader may later audit the review trail"
tags:
  - pr-review
  - discipline
  - false-positives
  - codex
  - copilot
  - gemini
  - coderabbit
---

# Reply-to-every-comment discipline and declining bot false positives

## Context

Across PRs #5, #6, #7 (2026-04-07), ~40% of bot findings were accepted and fixed, ~50% were nit/P3 deferred, and ~10% were declined as false positives. Without an explicit reply discipline, declined comments look identical to "missed" comments in the GitHub UI — a future auditor (human or agent) cannot tell whether a concern was considered or overlooked.

The discipline: **reply to every bot comment, every time, with one of three intents: fixed, deferred-with-rationale, or declined-with-rationale.** No silent drops.

## Guidance

### Three reply intents, always one of them

1. **Fixed.** Short reply naming the commit SHA and the file(s) touched. `Fixed in abc1234 — updated middens/src/techniques/thinking_visibility.rs to handle the None case.`
2. **Deferred.** Link to a todo file that captures the item with rationale. `Deferred to todos/batch4-coderabbit-deferred.md — P3, consider if profiling shows it matters.`
3. **Declined.** Explain *why* it is a false positive or intentional trade-off. Include falsifiable evidence (file paths, test counts, upstream constraints) so the reasoning can be re-checked later.

Use `gh api repos/<owner>/<repo>/pulls/<n>/comments/<id>/replies -f body="..."` to post inline replies — this threads under the original comment so the audit trail is obvious.

### Declining with evidence, not assertion

A decline is a claim that the reviewer is wrong. It must cite what makes it wrong, not just "this is intentional." Two worked examples from this session:

**Copilot PR #6 — GFM `||` table rendering hallucination.**
> Copilot flagged `||` at the start of a markdown table row as "empty first column."
>
> Declined with evidence: "The raw file uses single `|` leading pipes, not `||`. GitHub preview renders the table correctly — verified at <permalink-to-rendered-view>. Re-check only if a human reviewer reports an actual rendering issue."

The evidence is the rendered view, not a restatement of intent. A future auditor can click the permalink and verify in one step.

**Codex PR #7 — `thinking_visibility` step-module false positive.**
> Codex claimed a `thinking_visibility` step module needed registration in `tests/cucumber.rs`.
>
> Declined with evidence: "No such file exists. Thinking-visibility scenarios are served by the existing `thinking_divergence.rs` step module, which is already registered in `tests/cucumber.rs:14`. Current pass rate: 264/264 scenarios. `git grep thinking_visibility middens/tests/` returns zero results."

Three pieces of falsifiable evidence: file-not-found, actual registration site with line number, test count. A future agent can verify each in under a minute.

### Log declines in a deferred-items file

Even declines get a short entry in the per-batch deferred-items todo. Declined items are valuable precisely because they capture *reasoning that was challenged and survived*. Pattern:

```markdown
## Declined

- **<reviewer> PR #<n> <short title> (comment <id>):** <what was flagged>.
  Declined as <false positive | trade-off>; <one-line evidence>. Re-check if <trigger condition>.
```

The "Re-check if" clause is important — a decline is not forever, it is "not now, unless X." Naming X makes the decline reversible without requiring a fresh investigation.

## Why this matters

- **Auditability.** A silent drop and a deliberate decline look identical in retrospect. Reply discipline makes the decision legible to future you, other maintainers, and future agents picking up the thread.
- **Bot calibration.** Declined findings are training data. Patterns (Copilot hallucinates GFM syntax; Codex invents file paths from related symbols) become predictable and can be filtered faster in subsequent loops.
- **Protection against drift.** When a decline is logged with a "re-check if" clause, a later change that trips that clause is a known signal, not a surprise regression.
- **Morale / loop completion.** An unreplied comment nags at the orchestrator ("did I handle that one?"). Reply discipline provides a clear done-signal: `comments replied == comments fetched`.

## When to apply

- Every bot-reviewed PR
- Always — there is no "trivial enough to skip reply" threshold. The cost of a reply is seconds; the cost of a silent drop compounds

## Examples

See `todos/batch4-coderabbit-deferred.md` for the live pattern — Declined section with evidence-based rationale and "re-check if" clauses for Copilot and Codex false positives.

## Related

- `docs/solutions/workflow-issues/multi-round-bot-review-convergence-20260407.md` — when to stop iterating
- `docs/solutions/workflow-issues/atomic-per-round-commits-and-multi-pr-branch-routing-20260407.md` — how to structure the fixes these replies reference
- `docs/solutions/workflow-issues/automated-pr-review-triage-workflow-20260404.md` — underlying fetch/reply mechanics
