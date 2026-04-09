---
status: proposed
priority: P3
tags: [technique, nlp, register, tone, meta]
source: conversation 2026-04-09
---

# Register Drift Detection — "Is the agent taking itself too seriously?"

## The observation

Agents (Claude included) drift toward a pompous, earnest, research-grant register when writing READMEs, project descriptions, commit messages, and user-facing prose. Phrases like "studying X at scale through multi-disciplinary Y" appear unprompted. The user's natural register is lighter and self-deprecating, and the drift requires manual correction every time.

This is a measurable behavioral phenomenon in the corpus, not just a pet peeve. It sits at the intersection of:

- **Sycophancy / safety-training artifacts** — models trained to sound competent default to ceremonial prose.
- **Register mismatch** — the agent's prose register diverges from the user's, and corrections accumulate.
- **Thinking vs text divergence** — likely a sibling of the 100% risk-suppression finding (PR #7): what the agent *thinks* about the work and what it *writes* for the user are stylistically different populations.

## Why it's worth a technique

1. **Corrections-as-signal.** The corpus already has correction events. A "tone correction" is distinguishable from a "logic correction" and probably forms its own cluster. If we can classify it, we can measure how often agents need to be told to chill out.
2. **It generalizes.** Register drift is one instance of a broader phenomenon: agents reverting to a training-distribution voice even when the local context (CLAUDE.md, prior user messages, project README) clearly establishes a different register. Detecting that drift is useful beyond prose — the same mechanism likely governs over-apologizing, over-hedging, and over-structuring.
3. **It's actionable.** A signal that flags "this session had N register corrections" lets us measure whether CLAUDE.md rules like "prose should be light" actually take hold or get ignored.

## What to build

A Python technique (probably) that, per session:

1. **Classifies user messages** into `register_correction` vs other correction types. Heuristics to start:
   - Lexical cues: "less pomp", "don't take yourself too seriously", "lighter", "drop the", "too formal", "fix it for you", "there,", meta-level complaints about tone rather than content.
   - Structural cues: user edit that replaces phrasing without changing semantics (diff-based — short substitution within a sentence, no new facts).
2. **Classifies agent outputs** for pompous-register markers. Candidate features:
   - Ceremonial n-grams ("at scale", "multi-disciplinary", "rigorous", "robust framework", "leveraging", "empowering", "end-to-end").
   - Sentence length distribution (ceremonial prose skews long).
   - Nominal/verbal ratio (nominalization — "the implementation of" vs "implementing").
   - Abstract-noun density.
3. **Measures drift** — a session-level score: proportion of agent prose messages in the top quartile of ceremonial-register features, weighted by whether they precede a register correction from the user.
4. **Compares against the user's own register** — baseline the user's typical sentence length, n-grams, and self-deprecation markers from their messages in the same corpus. Drift is the *delta*, not an absolute score.

## Things to figure out before writing code

- **English-only.** Add to the `language_gate` list alongside `thinking-divergence`, `correction-rate` P3, and `user-signal-analysis`. See `todos/multilingual-text-techniques.md`.
- **Corpus-wide baseline vs per-user baseline.** Per-user is more honest (register is personal) but sparser. Start corpus-wide, add per-user if fixture counts allow.
- **Operator personality confound.** A user who never corrects tone isn't necessarily working with a non-drifting agent — they may not care. The signal is "drift relative to user preference as expressed in their corrections and CLAUDE.md files." Needs access to the CLAUDE.md content as a regressor.
- **Stratify, as always.** Visible vs redacted thinking, interactive vs subagent, en-only, temporal window. Per the compound-scoping rule.
- **Prior art.** Search for stylometry, register analysis (Biber's register dimensions), formality detection (Pavlick & Tetreault 2016), sycophancy benchmarks (Sharma et al. 2023). Add to `docs/methods-catalog.md` when implemented.

## Open questions

- Is this one technique or two? A "ceremonial-prose detector" (agent-side feature extraction) and a "register-correction classifier" (user-side correction classifier) could be decoupled and composed.
- Does the phenomenon show up in commit messages specifically? Commit messages are a clean test bed — short, frequent, and the "pompous" version is easy to spot ("chore: implement the comprehensive overhaul of..." vs "fix: typo").
- Is this just a special case of the thinking-divergence finding? The agent's internal voice and user-facing voice may diverge stylistically in the same way they diverge on risk. Worth checking whether register drift correlates with `thinking_visibility`.

## Deliverables when this lands

- `middens/python/techniques/register_drift.py` (or split into two)
- Gherkin feature file with fixtures covering (a) corrected register, (b) uncorrected register, (c) user who never corrects
- Methodology entry in `docs/methods-catalog.md`
- If the corpus confirms the phenomenon: a short report in `docs/reports/` and a new row in the headline-findings table
