---
module: corpus
date: 2026-04-07
problem_type: best_practice
component: documentation
severity: high
tags: [corpus, stratification, autonomous-sessions, boucle, contamination]
applies_when:
  - discovering a concentrated cluster of anomalous sessions in the corpus
  - a lexical or structural marker correlates with a dramatic behavioral shift
  - deciding between "filter out" and "stratify as first-class"
---

# The Boucle W10–W12 cluster is a stratum, not contamination

## Context

During the Batch 4 tool-rate analysis, weeks W10–W12 showed a collapse
from the long-run mean of ~572 tool calls per session down to ~8.9. The
surface explanation was contamination: 1,820 out of 1,826 sessions in
the cluster carried an explicit `queue-operation` marker, and the
natural reflex was to filter them and move on.

Looking more carefully, the real smoking gun was not the marker. It was
that **100% of the affected sessions had zero tool calls at all**. The
`queue-operation` string is a label; the zero-tool-rate is a behavioral
signature. Those are two different claims, and conflating them nearly
sent us down a filter-and-forget path.

## Guidance

When a concentrated corpus cluster shows a categorically different
behavioral profile from the surrounding sessions, the default move is
**not** to filter it. The default move is to ask whether it constitutes
a new stratum worth studying in its own right.

For Boucle W10–W12 specifically:

- The cluster is coherent (same marker, same temporal window, same
  zero-tool signature).
- The behavior is qualitatively distinct from both interactive and
  subagent sessions — agents running in a fully autonomous loop with
  no tool surface exposed.
- It is large enough (N ≈ 1,820) to power its own analyses.
- It is the first example in the corpus of an "Autonomous" session
  type, and future corpora are likely to include more of them as
  autonomous-loop products ship.

Promote it to a first-class stratum in the session_type axis:

    session_type ∈ { interactive, subagent, autonomous, mixed }

Do not silently exclude it. Tag it, stratify it, and run the full
technique battery against it as a cohort.

## Why This Matters

The framing change is load-bearing. "Contamination to filter" buries
the most interesting behavioral cluster we have found to date. It is
the only cohort where we can study agent behavior in the absence of a
tool surface — a natural ablation that would be expensive to
manufacture deliberately. Filtering it would throw away the control
condition for every tool-use finding in the corpus.

It also changes how we describe the Batch 4 rate collapse. The old
framing was "572 → 8.9, investigation pending." The new framing is
"the blended denominator was averaging two populations with
incompatible tool surfaces, and the right number is a pair: ~572 for
interactive+subagent, 0 for autonomous." The blended 8.9 is not a
finding — it is the arithmetic mean of two numbers that shouldn't have
been averaged.

This is the same failure mode as the 85.5% risk-suppression case, just
with a different axis (session_type instead of thinking_visibility).
Both resolve by refusing to mix populations in the denominator.

## When to Apply

- An anomaly cluster has a coherent marker AND a coherent behavioral
  signature — treat the behavioral signature as the defining
  property, not the marker.
- The cluster is large enough to stratify against.
- "Filtering it out" would require justifying why the sessions are
  invalid rather than merely different.

## Examples

**Wrong framing:**

> W10–W12 contaminated by queue-operation sessions; filter and rerun.
> Corrected tool rate: 572.3/session.

**Right framing:**

> scope: session_type=autonomous, thinking_visibility=…, language=en,
>        temporal_window=W10–W12
> N = 1,820 ; defining signature = zero tool calls, queue-operation marker
> Treat as new first-class stratum. Run full technique battery
> against it as its own cohort. The "572" number applies only to
> session_type ∈ {interactive, subagent}.

Related:
- `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`
- `docs/solutions/methodology/compound-scoping-rule-4-axis-stratification-20260407.md`
