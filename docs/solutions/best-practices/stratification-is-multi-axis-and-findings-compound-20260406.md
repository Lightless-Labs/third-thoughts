---
title: "Stratification is multi-axis; headline findings must be scoped on all axes at once"
module: third-thoughts
date: 2026-04-06
problem_type: research_methodology
component: corpus-stratification
severity: critical
status: accepted
tags:
  - stratification
  - population-contamination
  - headline-findings
  - research-integrity
  - compound-scoping
---

# Stratification is Multi-Axis

## The lesson (one paragraph)

A headline finding on an agent-behavior corpus is honest only when it is scoped on **every axis that has been shown to shift the result**. Third Thoughts has now watched the same "85.5% risk suppression" finding move under **four distinct stratification axes discovered at different times**, in three cases ending up either retracted or dramatically different. The operational rule: **every new stratification axis you discover is a scope narrowing for all existing findings**, not just a filter for new work. Past findings must be re-run under the union of all known axes before they can be cited.

## The four axes (as of 2026-04-06)

| Axis | Discovered | How it bites | Representative retraction or movement |
|---|---|---|---|
| **`session_type ∈ {Interactive, Subagent}`** | 2026-03-20 | Subagent sessions wrap tool results as user messages; lexical classifiers lit up on tool_result content and inflated apparent correction rates. "Thinking blocks prevent corrections" went from p=10⁻⁴² to p=0.40 under the split. | `thinking blocks prevent corrections` — RETRACTED |
| **`thinking_visibility ∈ {Visible, Redacted, Unknown}`** | 2026-04-06 (PR #7) | The UI-only `redact-thinking-2026-02-12` beta header hides thinking from local transcripts starting 2026-02-12. Sessions after the rollout with no thinking blocks score 0% suppression trivially, dragging mixed-corpus means down. | `85.5% risk suppression` → **100% on visible-only** (N=828, 4,819 risk tokens). The number moved UP, not down. |
| **`language ∈ {en, other}`** | 2026-04-06 | `thinking-divergence` RISK_TOKENS and `correction-rate` Priority-3 lexical layer and `user_signal_analysis` patterns are all literal English. Non-English sessions silently score 0% on everything. Most middens techniques are language-invariant (tool-sequence based) — only the ones that look at user text are affected. | Remediation pending (`todos/multilingual-text-techniques.md`). Expected effect: small, because the corpus is mostly English — but the scope narrowing is still required. |
| **`session_type ∈ {Interactive, Subagent, Autonomous}`** | 2026-04-06 (PR #6) | The "interactive" stratum is contaminated with autonomous agent loop iterations (Boucle in this corpus; probably others in other corpora). Zero tool calls, queue-operation type messages, no human participation. Dragged temporal statistics into nonsense after W09. | 45× session count explosion / 64× tool-rate collapse in W10–W12 — confirmed contamination, not model regression. Autonomous stratum planned (`todos/autonomous-session-stratum.md`). |

## Why this matters (beyond just this corpus)

**Any finding reported on a "mixed corpus" is a claim about the joint distribution of the corpus, not about the phenomenon under study.** If the composition shifts — because of a UI change at the vendor (axis 2), a user-language shift (axis 3), or a new framework category entering the dataset (axis 4) — the finding's numeric value shifts mechanically without anything changing about the underlying phenomenon.

This is not a novel insight in statistics. But it bites harder in agent-behavior research than in most fields because:

1. **The axes are not known in advance.** We discovered axis 2 because of a single comment on a GitHub issue. We discovered axis 4 because a replication study produced nonsense numbers. Neither was anticipated during the original analysis.
2. **The vendor can silently change the joint distribution.** A beta header rolled out at a fixed date will reshape every future corpus, and nothing in the session file signals "this session was captured after the rollout" — we had to infer it from timestamps.
3. **The frameworks change shape.** Autonomous agent frameworks wrap their loops in whatever message format they please, and if that format happens to match interactive sessions structurally, the corpus classifier will silently mis-bucket them.
4. **The findings are interesting to readers** — risk suppression, pre-failure states, session degradation. High-visibility findings are exactly the ones where being wrong is most costly.

## The operational rule

**When you discover a new stratification axis, you do not just filter on it going forward — you re-run every prior headline finding under the new axis.** If the finding moves materially, update or retract. If it doesn't move, document that it survived the new axis (this is valuable — survived findings are stronger evidence than unstratified ones).

Concretely, in Third Thoughts:

- Maintain the axis list in `docs/HANDOFF.md` under "Compound scoping rule." Currently four axes: `session_type` (3-way), `thinking_visibility` (3-way), `language` (binary), `temporal_window`.
- Every `docs/reports/*.md` headline must state its scope explicitly, e.g.: "100% risk suppression (N=828, 4,819 risk tokens, 209 paired messages; scope: `language=en AND thinking_visibility=Visible AND session_type=Interactive AND NOT contaminated_by_Boucle`)."
- When a new axis lands, grep for every prior headline and tag it for re-validation. Findings that can't be re-run (because the axis can't be applied retroactively) should be downgraded in confidence.
- `middens analyze --split` should eventually produce stratified output on all 4 axes at once. Currently only session_type × `--split` is implemented; the rest are per-technique guards.

## A secondary rule: numbers move in both directions

**It is tempting to assume stratification always weakens findings. It does not.** The 85.5% → 100% case in PR #7 is the clearest example: when redacted sessions (which trivially score 0%) are properly excluded from the denominator, the headline figure moves UP. Naive stratification adds scope constraints and weakens confidence per-observation. Principled stratification removes mixed-population artifacts and often strengthens the underlying claim within the narrower scope.

If your stratification changes a finding's magnitude, ask: "did the population change or did the phenomenon change?" The population changed. The phenomenon didn't. What changed is that you now know which population you're talking about.

## Application to future Third Thoughts work

This learning motivates two concrete changes in the project:

1. **New work must pre-declare its scope on all 4 axes** in the NLSpec or brainstorm doc. The tech-debt of retrofitting scope constraints onto prior findings is the cost of not having done this from day 1; future work can avoid paying the same cost by declaring scope upfront.
2. **Every technique in `middens/src/techniques/` and `middens/python/techniques/` should eventually carry a scope guard** — at minimum, a comment stating which axes it is sensitive to and which it is invariant under. Language-invariant techniques (markov, entropy, etc.) are safe for multilingual corpora; the text-based ones are not. Thinking-dependent techniques need the `thinking_visibility` axis. Session-type-dependent techniques need the 3-way split. **This should go in the method catalog** (`docs/methods-catalog.md`).

## Cross-references

- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` (axis 1)
- `docs/solutions/methodology/redact-thinking-stratification-20260406.md` (axis 2)
- `todos/multilingual-text-techniques.md` (axis 3)
- `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md` (axis 4)
- `todos/autonomous-session-stratum.md` (axis 4 remediation)
- `docs/HANDOFF.md` "Compound scoping rule"
