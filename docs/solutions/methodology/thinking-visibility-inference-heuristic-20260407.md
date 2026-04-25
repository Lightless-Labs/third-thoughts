---
module: classifier
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [stratification, thinking-blocks, inference, classifier, heuristic]
applies_when:
  - classifying a session's thinking_visibility axis for stratification
  - the raw session log lacks an explicit visibility marker
  - building or maintaining session parsers and classifiers
---

# Thinking-visibility inference heuristic

## Context

The 4-axis compound scoping rule requires every session to declare a
`thinking_visibility` label. In practice, sessions do not carry an
explicit flag — we have to infer visibility from the presence of
thinking content blocks, combined with the session's temporal
position relative to the Claude Code redaction cutoff.

The inference is not complicated, but it needs to be the **same**
inference everywhere. Different analyses silently implementing
slightly different heuristics is how the denominator collapses
started in the first place.

## Guidance

Canonical inference rule, to be implemented once in
`middens::classifier` and reused by every technique:

    if session contains any `thinking` content block:
        thinking_visibility = Visible
    elif session has no thinking AND all timestamps are pre-cutoff:
        thinking_visibility = Visible     # visibility era, agent just didn't think
    elif session has no thinking AND any timestamp is post-cutoff:
        thinking_visibility = Redacted    # could be either, treat as unobservable
    elif session has no timestamps at all:
        thinking_visibility = Unknown     # exclude from any thinking-dependent rate

The asymmetry matters: a session with zero thinking blocks in the
visibility era is genuinely a "did not think" observation and
contributes a real zero to the numerator. The same session in the
redacted era is structurally unobservable and must be excluded from
the denominator entirely (see the visible-only denominator rule).

The cutoff date is a single constant maintained in one place.
Whenever the provider changes its redaction policy, that constant
moves and every downstream technique re-derives its labels
consistently.

**Codex/pi caveat (2026-04-25):** `thinking_visibility` describes raw
thinking visibility, not every form of reasoning observability. Codex/pi traces
can contain encrypted reasoning signatures plus provider-selected plaintext
summaries on a per-turn basis. Those summaries must not be treated as raw
`thinking` blocks; use the separate `reasoning_observability` and
`reasoning_summary` fields documented in
`docs/solutions/methodology/codex-adaptive-reasoning-observability-20260425.md`.

## Why This Matters

Without a single authoritative heuristic, each technique ends up
reinventing the rule with subtle differences: one counts missing
thinking as zero, another excludes it, a third conditions on a
different cutoff date. The resulting cross-technique numbers cannot
be combined, and the 4-axis scoping rule becomes unenforceable
because two analyses claiming the same scope may actually be using
two different definitions of it.

Pinning the inference rule in the classifier also makes the "could
be either" ambiguity in the post-cutoff no-thinking case explicit.
The conservative choice (treat as Redacted) trades a small numerator
loss for full denominator hygiene, and it is the right trade
everywhere we have tested it.

## When to Apply

- Any technique that reads `thinking` blocks or computes a rate over
  sessions where thinking might be missing.
- Any parser or classifier touching session metadata.
- Any cross-technique aggregation that assumes consistent scope
  labels.

## Examples

**Consistent use:**

    session.thinking_visibility = classifier.infer_thinking_visibility(session)
    if session.thinking_visibility != Visible:
        continue   # exclude from visible-only denominator

**Anti-pattern (don't do this):**

    # Technique A
    if not session.has_thinking: rate_denom += 1   # counts as zero

    # Technique B (same corpus, different denominator)
    if not session.has_thinking: continue          # excludes

These two techniques will report incompatible rates over the same
cohort, and a reader comparing them will see a phantom effect.

Related:
- `docs/solutions/methodology/codex-adaptive-reasoning-observability-20260425.md`
- `docs/solutions/methodology/redact-thinking-stratification-20260406.md`
- `docs/solutions/methodology/visible-only-denominator-risk-suppression-20260407.md`
- `docs/solutions/methodology/compound-scoping-rule-4-axis-stratification-20260407.md`
