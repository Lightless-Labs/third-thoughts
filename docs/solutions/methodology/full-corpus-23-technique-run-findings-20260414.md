---
title: "First clean 23/23 technique run: what held, what collapsed, what's new"
date: 2026-04-14
category: methodology
module: third-thoughts
problem_type: best_practice
component: documentation
severity: high
applies_when:
  - "Citing any of the headline findings from the 2026-04-14 full-corpus run"
  - "Evaluating whether a prior finding needs re-scoping or retraction"
  - "Planning next analysis steps after the 23-technique battery"
tags: [corpus-analysis, findings, risk-suppression, HSMM, MVT, correction-dynamics, sequential-patterns, epistemic-networks, stratification, 23-techniques]
---

# First clean 23/23 technique run: what held, what collapsed, what's new

## Context

On 2026-04-14, `middens analyze` completed its first ever clean run across all
23 techniques on the full corpus: 13,423 sessions, zero errors, zero timeouts.
This is the first time all 23 techniques have produced output simultaneously on
production data, making it the most comprehensive single snapshot of the corpus
to date.

What follows is a findings summary — what replicated, what didn't survive the
larger sample, what's new, and what's methodologically suspect. Numbers are from
the unstratified mixed corpus unless noted. All claims that don't survive the
compound scoping rule (4-axis stratification) are flagged.

Synthesis source: `~/middens-analysis-2026-04-14/interpretation.md`, generated
by Opus 4.6 from the 23 technique output files.

---

## Key Findings

### Risk suppression replicates — now on N=4,518

The headline finding holds: **99.99% risk suppression** (31,677/31,679 risk
tokens in thinking blocks absent from paired user-facing text). Only 2 tokens
leaked across 31,679 observations — an effective leak rate of 0.006%, which is
"complete suppression" for any practical purpose.

Prior provisional finding (PR #7): 100% on N=828 visible-thinking sessions,
4,819 risk tokens. This run: same rate, 4,518 visible sessions, 31,679 risk
tokens. The larger sample strengthens the finding rather than eroding it.

The thinking-to-text divergence ratio is 703:1 — thinking blocks contain 703×
more character content than paired user-facing text. Agents think a lot and say
very little. (Whether this is efficiency or anxiety is left as an exercise.)

**Scope:** `session_type=any, thinking_visibility=Visible, language=en` (7,907
redacted-thinking sessions excluded; 7 unknown-visibility sessions flagged).
Still needs per-project stratification — 93.6% corpus concentration means
"corpus-wide" is mostly three projects.

**Granger footnote:** `message_length` Granger-causes `thinking_ratio` (p=0.0003),
and `correction_indicator` Granger-causes `thinking_ratio` (p=0.019). But
`thinking_ratio` does not Granger-cause anything — not corrections, not tool
diversity, not message length. Thinking is a *response* to complexity, not a
*predictor* of outcomes. The retracted "thinking blocks prevent corrections"
finding remains correctly retracted.

---

### HSMM pre-failure lift: 24.6x → 2.15x (direction holds, magnitude does not)

The Hidden Semi-Markov Model fit 5 states across 495,561 assistant turns. The
pre-correction lift for the "minimal output" state (State 1) is **2.15x** — a
substantial drop from the prior headline of 24.6x.

The direction replicates: there is a detectable pre-failure signature. The
magnitude does not: 2.15x is real but not as dramatic as 24.6x made it sound.

**Likely cause of the drop:** The prior 24.6x result was from the mixed corpus
before the W10-W12 Boucle contamination was characterised. Those 1,820
zero-tool-call sessions would cluster into a single HSMM state and produce
extreme lift by construction. The 24.6x headline was probably a corpus
composition artifact, not a behavioural signal.

**Status:** Downgrade from "robust (mixed corpus)" to "provisional — needs
Boucle-excluded re-run". If lift recovers to >10x after excluding
`autonomous-sandbox` W10-W12 sessions, the original finding may be partially
rescued.

---

### MVT violation: 0% compliance (robust replication)

Marginal Value Theorem compliance rate: **0%**. Zero sessions comply with the
optimal foraging prediction. This replicates robustly from the prior mixed-corpus
analysis — agents consistently under-stay in patches relative to the optimal
departure threshold.

Stats: mean 6.3 patches per session, mean residence time 1.49 turns, patch
revisit rate 37.5%, explore:exploit ratio 2.58, foraging efficiency 8.4%.

The success/struggle comparison is counterintuitive: low-correction sessions
have *longer* residence times (1.55 vs. 1.12 turns) but *lower* foraging
efficiency (7.5% vs. 14.0%). High-correction sessions look more efficient
because users redirect agents to specific locations, which concentrates tool
calls on user-specified targets and inflates the efficiency metric.

---

### Correction dynamics: corrections front-load, sessions improve over time

**18.2%** of sessions (2,440/13,423) contain any user correction. Of those,
corrections concentrate in the first third: **first-third rate = 0.068** vs.
0.014 (middle) and 0.019 (last). Mean degradation ratio: **0.20x** (last-third /
first-third) — corrections *decrease* over time, not increase.

This contradicts a naive "agents get worse over time" story. The more plausible
interpretation: users course-correct early and the agent gets on track, or users
stop correcting (which looks the same in the data). Sessions improve over their
own lifetime, even if the corpus-wide correction rate drifts upward over calendar
time (both can be true).

Cox survival model: **subagent sessions have 3.28x the correction hazard**
(p~0), while **having thinking blocks cuts hazard by 41%** (exp(coef)=0.59,
p~0). Concordance = 0.76.

---

### Sequential motifs: UWUW = success, UUX = struggle, UC→UC self-reinforces

From Smith-Waterman alignment (n=50, generalise with caution):

- **UWUW** (user-write-user-write): 13.7x enrichment in low-correction sessions
- **UUX** (user-user-error): 6.9x enrichment in high-correction sessions
- **Conserved motifs** (UTU, TUU, UTUU — user-tool-user sequences): present in
  34% of sessions

From lag-sequential analysis: corrections self-reinforce — UC→UC at lag-2 has
z=889.5. When a user starts correcting, they keep correcting within a temporal
window.

---

### Epistemic networks: EVIDENCE_SEEK ↔ SELF_CORRECT discriminates success

ENA coded 10,563 sessions. Most central code: **SELF_CORRECT** (centrality=0.198),
tied with EVIDENCE_SEEK.

- **Low-correction sessions**: dominated by `EVIDENCE_SEEK <-> SELF_CORRECT`
  (weight 0.518 vs. 0.032) and `PLAN <-> SELF_CORRECT` (0.363 vs. 0.019).
  Successful agents self-correct while seeking evidence.
- **High-correction sessions**: dominated by `EVIDENCE_SEEK <-> PLAN` (0.515
  vs. 0.267) and `PLAN <-> PROBLEM_FRAMING` (0.509 vs. 0.241). Struggling
  agents plan and frame without self-correcting.

Takeaway: **self-correction co-occurring with evidence-seeking is the signature
of agent success**. Plan-frame-plan loops without self-correction predict user
intervention.

---

### Tool use: highly repetitive and bursty (robust, expected)

Aggregate burstiness coefficient B=0.59. Self-loop rates: Bash 76.7%,
WebSearch 74.2%, TaskCreate 79.9%. **58.8% of sessions are monocultures**
(evenness < 0.3). Median Shannon entropy = 0.000.

PrefixSpan found 107 frequent patterns; top ones are `Read→Read→Read` (69.2%),
`Bash→Bash→Bash` (55.2%). The agent's favourite move is to keep doing whatever
it's already doing.

**Artifact note:** The monoculture rate is likely inflated by the subagent
population (~50% of corpus). Subagents operate with narrow, single-tool mandates
by design. Needs stratification before citing as a behavioural finding about
interactive sessions.

---

## Known Artifacts and Contamination

1. **Corpus concentration:** 93.6% of sessions from 3 projects (`subagents`,
   `autonomous-sandbox`, `the-daily-claude`). Corpus-wide statistics are a
   weighted average of those three projects' behaviour. Findings that don't
   survive per-project stratification are suspect.

2. **W10-W12 Boucle contamination:** 1,820 zero-tool-call sessions from
   `autonomous-sandbox` remain in the corpus. They pull down diversity metrics,
   inflate monoculture counts, and likely caused the 24.6x HSMM lift.

3. **Frustration classifier pile-up:** 90% of messages classified at intensity 2.
   This is a calibration failure — intensity 2 is "normal task instruction," not
   mild frustration. The 3,084 escalation sequences and frustration-related
   findings are unreliable until recalibrated.

4. **Single-user corpus:** Convention epidemiology and "population-level" analysis
   are actually single-user-level. The logistic fit for tool-use convention
   adoption is real; the interpretation as "propagation between projects" is
   misleading — it's one person's workflow habits carried across repos.

5. **Interactive/subagent mixing:** Subagent "corrections" in the Cox model may
   be system-level routing, not user dissatisfaction. The 3.28x hazard for
   subagents should be treated with caution until stratified.

---

## Compound Scoping Reminder

Per the compound scoping rule
(`docs/solutions/best-practices/stratification-is-multi-axis-and-findings-compound-20260406.md`),
every headline number from this run should be scoped on:

1. `session_type ∈ {Interactive, Subagent, Autonomous}`
2. `thinking_visibility ∈ {Visible, Redacted, Unknown}`
3. `language ∈ {en, other}`
4. Temporal window (ISO week, pre/post rollout)

The risk suppression finding is the only one here that has been properly scoped
(thinking_visibility=Visible, language=en). Everything else is unstratified
mixed-corpus numbers. Cite accordingly.

---

## Recommended Next Steps

Ranked by blocking impact:

1. **Stratify everything by session_type + project** — the 93.6% concentration
   makes most corpus-wide numbers uninterpretable without it. Blocking.
2. **Re-run HSMM with Boucle contamination excluded** — diagnose the 24.6x →
   2.15x collapse. If it recovers, the pre-failure signature is real. If it
   doesn't, the 24.6x headline was contamination all the way down.
3. **Recalibrate frustration classifier** — the intensity-2 pile-up makes
   escalation analysis unreliable. Medium priority.
4. **Validate Granger causality on interactive-only, visible-thinking subset** —
   the "thinking is reactive, not predictive" result is important enough to
   warrant a clean replication on the right population. Low-medium priority.

---

## Related

- `docs/solutions/methodology/visible-only-denominator-risk-suppression-20260407.md` — the 85.5%→100% reframe that this run's 99.99% number builds on
- `docs/solutions/methodology/autonomous-stratum-boucle-w10-w12-20260407.md` — the W10-W12 contamination that likely explains the HSMM lift collapse
- `docs/solutions/best-practices/stratification-is-multi-axis-and-findings-compound-20260406.md` — compound scoping rule
- `docs/solutions/methodology/redact-thinking-stratification-20260406.md` — visible-only denominator methodology
- `~/middens-analysis-2026-04-14/interpretation.md` — full Opus 4.6 synthesis of all 23 technique outputs
