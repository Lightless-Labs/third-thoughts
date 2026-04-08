---
module: analysis
date: 2026-04-07
problem_type: best_practice
component: documentation
severity: high
tags: [stratification, risk-suppression, denominators, thinking-blocks, headline-findings]
applies_when:
  - reporting aggregate rates on a corpus that mixes redacted and visible sessions
  - computing any "X% of sessions show behavior Y" where Y depends on a signal that can be structurally absent
  - headline statistics move unexpectedly after filtering
---

# Visible-only denominator: the 85.5% → 100% risk-suppression reframe

## Context

The headline "85.5% risk suppression" finding replicated four times across the
Third Thoughts corpus and was the single most robust result we had. When we
re-ran the analysis on the visible-thinking stratum only, the rate jumped to
effectively 100%. Nothing about the underlying behavior changed — the
denominator did.

Redacted sessions (post-cutoff Claude Code, thinking blocks stripped) cannot
exhibit the signal at all. They were scoring 0% not because agents weren't
suppressing risk, but because the measurement instrument could not see
anything. Including them in the denominator dragged the aggregate down by
exactly the fraction of redacted sessions in the mix.

## Guidance

When a measurement depends on a signal that can be structurally absent from
some sessions, compute the rate only over sessions where the signal is
**observable**. Redacted-thinking sessions are not zeros — they are missing
data, and they belong in the "excluded: instrument blind" bucket, not in the
denominator.

Concretely for Third Thoughts:

- Any technique that reads `thinking` content blocks must report two numbers:
  the visible-stratum rate and the size of the excluded redacted stratum.
- The "headline" number is always the visible-only rate. The mixed-corpus
  rate is a footnote that quantifies how much the instrument is blinded, not
  a finding in its own right.
- Retractions are cheap; inflated denominators compound into downstream
  claims (survival curves, HSMM state lifts, correction-rate deltas) that
  are much harder to walk back.

## Why This Matters

The 85.5 → 100 shift is not a small correction. It changes the framing from
"most agents suppress risk" to "every visible-thinking agent we have
evidence for suppresses risk." The phenomenon is categorical, not
probabilistic. Any mitigation research, safety claim, or training-signal
argument built on the 85.5 number was underselling the effect and
mis-specifying the population it applied to.

More generally, a blended denominator will quietly bias any rate
downward whenever the "invisible" subpopulation grows — and for Claude
Code specifically, the redacted fraction grows monotonically over
calendar time as the cutoff recedes. A 2026-Q2 rerun on the same
methodology would have drifted further without the denominator fix.

## When to Apply

- The signal being measured lives in a content channel that some sessions
  structurally lack (thinking blocks, tool_use blocks, specific system
  prompts, a particular provider's metadata).
- A finding's rate is surprisingly stable across reruns but drifts when
  the corpus time window extends.
- You are about to publish a headline percentage from a mixed-visibility
  corpus.

## Examples

**Wrong (mixed-corpus):**
`risk_suppressed / all_sessions = 0.855`
(numerator = 6,795 visible-with-suppression; denominator = 7,942 all)

**Right (visible-only):**
`risk_suppressed / visible_thinking_sessions ≈ 1.00`
(numerator = 6,795; denominator ≈ 6,795 visible-thinking;
excluded = 1,147 redacted, reported separately as "instrument blind")

The reporting pattern for every thinking-dependent technique becomes:

    Visible stratum:   N = 6,795   rate = 100.0%
    Redacted stratum:  N = 1,147   (excluded — thinking not observable)
    Unknown stratum:   N = 0       (no timestamps)

See also: `docs/solutions/methodology/redact-thinking-stratification-20260406.md`
for the upstream stratification decision this reframe is built on.
