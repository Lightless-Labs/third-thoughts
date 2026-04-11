---
title: Reviewer diversity dominates review iteration count
date: 2026-04-09
category: docs/solutions/methodology
module: review-process
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - reviewing a substantive spec, NLSpec, or design doc
  - deciding whether to run "another pass" of the same reviewer
  - one reviewer is misbehaving and you're tempted to compensate with more passes elsewhere
  - planning a review budget for a non-trivial artifact
tags: [code-review, spec-review, reviewer-diversity, delegation, methodology]
---

# Reviewer diversity dominates review iteration count

## Context

During the CLI triad NLSpec review (`docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md`, section 6), we ran four review passes across three reviewers: CodeRabbit, Gemini 3.1 Pro, and Codex. The three reviewers did not find overlapping problems. They found *categorically different* problems, and the union of their findings was load-bearing — dropping any one reviewer would have shipped a spec with known P1 defects.

The tempting alternative — "just run CodeRabbit three times, it's fast and it works" — would have caught the cosmetic layer cleanly and missed most of the actual spec bugs. We know this because passes 2 and 3 of the same reviewer on a given document mostly re-surfaced already-fixed issues or produced diminishing noise, while the *first* pass from a fresh reviewer reliably surfaced a new category of problem.

This doc names the pattern so we stop second-guessing it when one reviewer is misbehaving and the easy fix is "run the healthy ones more."

## Guidance

For any substantive spec or design review, spend your budget on **reviewer diversity first, iteration count second**. Concretely:

1. **One pass across three reviewers with different strengths** beats three passes across one reviewer. Every time we've measured it, this hasn't been close.
2. Staff the three dimensions explicitly:
   - **Cosmetic / structural** — typos, numbering, cross-reference consistency, schema validation, field-name ambiguity. CodeRabbit is the current default.
   - **Logic / cross-section contradictions** — rules in section 2.1 that contradict rules in section 2.3, ordering/uniqueness confusions, substring-match footguns, parser branch contradictions. Gemini 3.1 Pro is the current default.
   - **Spec × existing-codebase** — does the spec contradict files already in the repo? Does it assume harnesses that don't exist? Codex is the current default *when* its skill auto-activation isn't broken.
3. **Only run a second pass** if the first pass produced a substantive amendment that could plausibly have introduced new issues. "More thoroughness" is not a reason — it's the weak lever.
4. **Corollary — don't patch a missing dimension with more iterations of the surviving ones.** If Codex is broken, do not run CodeRabbit twice and call it even. Dispatch a Claude subagent with repo access to cover the codebase-cross-check dimension instead. Missing a dimension entirely is strictly worse than running fewer passes on the healthy ones.

## Why This Matters

The three reviewers in the triad review didn't just find different *issues* — they found different *classes* of issue, and each class had at least one P1 that would have shipped without that reviewer:

- **CodeRabbit** caught `1432`/`1500` where the spec said `14-32`/`15-00`, an `<analysis-run-slug>` used before definition, `--format <jupyter|html|...>` angle-bracket notation implying choices when only `jupyter` is valid, and a workaround-1/workaround-3 numbering gap with no workaround 2.
- **Gemini 3.1 Pro** caught a Parquet file multiplicity rule in section 2.1 that contradicted the `List<TableRef>` data model in section 2.3, a PII substring-match footgun where matching on `text` would reject `context_length` and matching on `message` would reject `total_messages`, a cross-runner slug ordering bug where `<runner-slug>-<uuidv7>` makes "latest" non-deterministic because `claude-code-*` always sorts before `codex-*`, a same-millisecond UUIDv7 ordering gap where uniqueness doesn't imply ordering without a monotonic generator, and a parser contradiction where one paragraph said "no markers → `conclusions.md`" and another said "no markers → failure."
- **Codex** caught that `middens/tests/features/pipeline/split.feature` already exists in the repo but the amended spec never specified how `--split` interacts with the new storage layer, and that scenario 3's "fails at the type level" phrasing requires a `trybuild` harness this repo doesn't have (untestable as-written). Codex was the only reviewer that cross-referenced the spec against actual repo state.

No amount of re-running CodeRabbit would have found the Parquet-vs-TableRef contradiction. No amount of re-running Gemini would have found the missing `trybuild` harness. The dimensions are not substitutable.

The cost of skipping a dimension is the cost of shipping whatever P1s live in it. The cost of running a second pass on an already-covered dimension is wall-clock time and reviewer noise. These are not the same cost.

## When to Apply

- Any NLSpec, design doc, RFC, or plan where an error would be expensive to unwind downstream.
- Any review where you're tempted to "just run it again" because the first pass felt thin.
- Any situation where one of the three reviewers is broken and you're choosing between (a) fixing the reviewer, (b) substituting a Claude subagent for the missing dimension, or (c) compensating with extra passes on the healthy ones. (a) and (b) are both fine. (c) is the trap.
- Review budget planning — when you have time for *n* review invocations, spend them across *n* reviewers before spending them across *n* passes.

## Examples

**Wrong:**

> CodeRabbit is fast and Codex's skill activation is broken again, so let's just run CodeRabbit three times on the NLSpec and ship it.

This gets you typos, numbering, and cross-reference consistency. It does not get you the cross-section logic contradictions or the spec-vs-repo inconsistencies. Those ship.

**Right:**

> CodeRabbit pass 1 for cosmetic/structural. Gemini 3.1 Pro pass 1 for cross-section logic. Codex pass 1 for spec × codebase — or, if Codex is misbehaving, a Claude subagent with repo access covering the same dimension. Second pass only if the amendments from the first round were large enough to plausibly break something new.

**Also right (the misbehaving-reviewer case):**

> Codex's skill auto-activation is broken (see `docs/solutions/workflow-issues/codex-skill-auto-activation-20260409.md`). Instead of running Gemini a second time to compensate, dispatch a Claude subagent with `mode: bypassPermissions` and the spec + relevant repo paths, and ask it to do the spec-vs-codebase cross-check. Dimension preserved; budget unchanged.

## Related

- `docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md` — section 6 has the full four-pass review history this doc generalizes from
- `docs/solutions/workflow-issues/codex-skill-auto-activation-20260409.md` — the broken-reviewer case that motivated the corollary
- Companion doc being written in parallel on *review pass diminishing returns* — cross-reference once it lands
