---
module: analysis
date: 2026-04-07
problem_type: best_practice
component: documentation
severity: high
tags: [stratification, scoping, methodology, findings-discipline, reproducibility]
applies_when:
  - reporting any aggregate finding from the Third Thoughts corpus
  - comparing results across analyses or across reruns
  - writing a finding into reports/, HANDOFF.md, or CLAUDE.md
---

# The compound scoping rule: 4-axis stratification for every finding

## Context

Over the last several batches we have been bitten, in order, by:

1. Mixing interactive and subagent sessions (p=10⁻⁴² → p=0.40).
2. Mixing redacted and visible-thinking sessions (85.5% → 100%).
3. Mixing English and non-English sessions in lexical classifiers.
4. Mixing pre- and post-cutoff sessions when the provider's schema changed
   under us.

Each collapse looked like a different problem. They are the same problem
wearing four hats: a finding was reported without declaring the
sub-population it actually applies to, and a later rerun on a different
cut of the corpus exposed the gap.

## Guidance

Every finding in this project must declare, up front, where it sits on
four independent axes. No aggregate number ships without all four.

    session_type         ∈ { interactive, subagent, autonomous, mixed }
    thinking_visibility  ∈ { visible, redacted, unknown, mixed }
    language             ∈ { en, multi, <specific>, mixed }
    temporal_window      ∈ { pre-cutoff, post-cutoff, spanning, <date range> }

A finding is only comparable to another finding when **all four axes
match**. If any axis differs, the findings are about different
populations and must not be aggregated, averaged, or ranked against
each other without explicit re-stratification.

The rule compounds: the more axes you pin, the more transferable the
finding becomes. A claim scoped to
`(interactive, visible, en, pre-cutoff)` is much stronger than a claim
scoped to `mixed` on any axis, because the population is fully
specified and any future rerun can reproduce it exactly.

## Why This Matters

The recurring failure mode is not "we forgot to stratify." It is "we
stratified on the axis we noticed last, and assumed the others didn't
matter." Each of the four axes has, independently, flipped a headline
statistic by more than an order of magnitude in this corpus. The
prior that "this axis probably doesn't matter" has been falsified four
times. The compound rule is the cheapest way to stop relitigating it.

Writing the four axes into the finding's header also forces the
analysis to notice when its scope is silently `mixed` on some axis —
which is usually the moment the analysis should be paused and
redesigned, not reported.

## When to Apply

- Every technique result that produces a rate, a survival curve, a
  lift, or a p-value.
- Every entry in `experiments/*/` that is referenced from a report.
- Every row of the Key Findings table in `CLAUDE.md` and
  `docs/HANDOFF.md`.
- Every commit message that claims "X% of sessions" — the scope goes
  in the commit body.

## Examples

**Before (ambiguous):**

> Risk suppression rate: 85.5% (N=7,942)

**After (compound-scoped):**

> Risk suppression rate: 100.0%
> scope: session_type=interactive, thinking_visibility=visible,
>        language=en, temporal_window=pre-2026-02-15
> N = 6,795 ; excluded: 1,147 redacted, 0 unknown

**Before:**

> Agents degrade over long sessions.

**After:**

> Agents degrade over long sessions.
> scope: session_type=interactive, thinking_visibility=mixed,
>        language=en, temporal_window=full
> Note: holds on interactive-only; does not replicate on subagent.
> Re-scope pending for thinking_visibility split.

A finding whose scope cannot be written in four lines is not yet a
finding — it is a hypothesis.

See also:
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md`
- `docs/solutions/methodology/redact-thinking-stratification-20260406.md`
- `docs/solutions/methodology/visible-only-denominator-risk-suppression-20260407.md`
