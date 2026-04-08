---
title: "Per-batch deferred-items todo file with explicit decline rationale"
module: tooling
date: 2026-04-07
problem_type: best_practice
component: development_workflow
applies_when:
  - "Closing out a PR-review iteration with nit/P3/declined items"
  - "Wanting a durable record of considered-but-not-actioned findings"
  - "Passing state to the next session or to another agent"
tags:
  - todos
  - pr-review
  - deferred
  - rationale
  - handoff
---

# Per-batch deferred-items todo file with explicit decline rationale

## Context

When a multi-round bot review closes, three categories of findings remain:

1. **Fixed** — lives in commits and replies, no durable artifact needed beyond git history.
2. **P3 / nit follow-ups** — not blocking merge, but real enough to remember.
3. **Declined** — reviewer was wrong or trade-off chosen, and the reasoning should survive.

Categories 2 and 3 need a home. Left in PR comments, they are buried once the PR merges. Left in the orchestrator's head, they evaporate at session end. The working pattern, established in this session, is a **per-batch deferred-items todo file** in `todos/` with explicit sections for each category.

## Guidance

### File layout

One file per review batch (usually one file per session if the session spans multiple PRs on the same theme), at `todos/<batch-identifier>-deferred.md`:

```markdown
---
status: open
priority: P3
tags: [pr-review, deferred, <batch-tag>]
source: PR #<n>[, #<m>, ...] automated bot review
issue_id: null
---

# <Batch name> / PR #<n>–#<m> — deferred bot review items

<One-paragraph context: which PRs, which date, what was the scope.
Makes the file self-contained for a future reader.>

## Declined

- **<Reviewer> PR #<n> <title> (comment <id>):** <what was flagged>.
  Declined as <reason>; <one-line falsifiable evidence>. Re-check if <trigger>.

## Potential follow-ups (not blocking)

- <Actionable item with enough context to pick up cold>
- <Cross-reference to related open todo files where relevant>
```

### Rules for entries

**Every declined item cites evidence.** Not "this is intentional" — a file path, a grep result, a test count, a permalink. The evidence must be verifiable in under a minute by a future reader.

**Every declined item has a "re-check if" clause.** Declines are reversible. The clause names the trigger condition that should cause re-evaluation. Examples: "re-check if profiling shows it matters," "re-check if a human reviewer reports an actual rendering issue," "re-check if the step-module file actually appears in a future refactor."

**Follow-ups link to other todo files when relevant.** A deferred item that belongs to an ongoing workstream should cross-reference, not duplicate. Example: multilingual gating lives in `todos/multilingual-text-techniques.md`; the batch4 deferred file just points there.

**The file stays short.** If it grows beyond ~20 items, either promote items to standalone todos or graduate the whole batch to a workstream-scoped todo. The deferred file is a *holding area*, not a backlog.

### Lifecycle

- **Created:** when the bot-review loop closes on a batch of PRs.
- **Updated:** if a later session re-opens one of the PRs and produces new deferred items.
- **Resolved:** when every item has either been actioned or determined permanently moot. At that point, delete the file — do not leave "done" markers cluttering `todos/`. The git history preserves it.
- **Re-checked:** when a "re-check if" trigger fires in a future session, revisit the relevant decline entry first before treating the finding as new.

## Why this matters

- **Session handoff.** Without the file, deferred items live only in the departing session's context and die at compaction. With the file, the next session (or next agent) can pick up instantly.
- **Decline reversibility.** A declined finding with an evidence citation and a re-check trigger is a reversible decision. Without those, it is either forgotten or re-litigated from scratch every time.
- **Audit defense.** When a future regression traces back to a declined finding, the file proves the decline was *considered* and documents the trigger that should have caught the regression — turning a "why did we miss this?" into a "the trigger clause fires here, time to re-check."
- **Review discipline reinforcement.** Knowing there is a target file for declines makes the orchestrator more likely to actually write out the reasoning rather than hand-wave.

## When to apply

- End of every multi-round bot-review loop that closes with any deferred or declined items
- Any time the orchestrator is tempted to rely on memory or PR comments to track non-blocking findings

## Examples

### The canonical example from this session

`todos/batch4-coderabbit-deferred.md`. Three declined entries (Copilot GFM false positive, Codex step-module false positive, Gemini refactor trade-off), each with evidence and a re-check clause, plus three follow-ups linking to other todos. Five minutes to write, survives indefinitely.

## Related

- `docs/solutions/best-practices/pr-review-reply-discipline-and-declining-false-positives-20260407.md` — the reply-side of the same discipline
- `docs/solutions/workflow-issues/multi-round-bot-review-convergence-20260407.md` — when the loop closes and deferred items get written out
- `docs/HANDOFF.md` — session continuity doc that points at active todos/
