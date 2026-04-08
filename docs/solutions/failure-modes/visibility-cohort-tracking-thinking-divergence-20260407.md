---
module: middens
date: 2026-04-07
problem_type: logic_error
component: tooling
severity: medium
symptoms:
  - Thinking-divergence percentages computed against the wrong denominator
  - Sessions without thinking blocks silently counted as "not diverged"
  - Rates inflated or deflated depending on cohort composition
root_cause: logic_error
resolution_type: code_fix
tags: [cohorts, denominators, thinking-blocks, statistics, stratification]
---

# Cohorts Must Be Tracked Explicitly, Not Inferred From Absence

## Problem

`thinking_divergence` reports the fraction of sessions where the assistant's
thinking block diverges from the user-visible response. The first implementation
counted divergent sessions in the numerator and *all* sessions in the denominator.
But sessions with no thinking blocks at all can't diverge or agree — they're
outside the cohort entirely. Including them in the denominator systematically
deflates the rate, and the deflation size depends on how many thinking-free
sessions happen to be in the corpus.

## Symptoms

- Divergence rate reported as 12% on a corpus where 40% of sessions had no
  thinking blocks — true rate on the eligible cohort was ~20%.
- Rates shifted significantly when the same technique ran on different corpus
  slices, even when the underlying behaviour was identical.
- PR reviewer: "denominator doesn't match the population the statistic claims to
  describe".

## What Didn't Work

- Filtering sessions at the top of the technique — loses the total count needed
  to report cohort coverage ("N sessions analyzed, M eligible").
- Reporting only the raw counts and letting the reader compute the rate — punts
  the bug downstream to reports that then make the same mistake.

## Solution

Track **three** counters explicitly: total sessions seen, eligible sessions
(cohort), and positive sessions (numerator):

```rust
let mut total = 0;
let mut eligible = 0;   // sessions with >=1 thinking block
let mut diverged = 0;

for session in sessions {
    total += 1;
    if !has_thinking(session) { continue; }
    eligible += 1;
    if diverges(session) { diverged += 1; }
}

let rate = if eligible > 0 {
    diverged as f64 / eligible as f64
} else {
    0.0  // or None; decide deliberately
};
```

Emit all three numbers in the output. The cohort size is as load-bearing as the
rate itself.

## Why This Works

- The denominator matches the claim ("of sessions where divergence is possible,
  X% diverged") instead of silently redefining it.
- Cohort drift across corpus slices becomes visible instead of masquerading as
  behavioural change.
- Consistent with the project-wide stratification discipline documented in
  `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md`
  — same failure mode at a smaller scale.

## Prevention

- Any rate statistic must report its denominator. If a technique emits a single
  percentage without a count, treat it as incomplete.
- When eligibility depends on a data feature (has thinking blocks, has tool use,
  has length >= N), make the eligibility check a named function and call it from
  both the numerator and denominator paths — impossible to forget one side.
- Add a test fixture that mixes eligible and ineligible sessions 50/50 with a
  known rate on the eligible half. A denominator bug will shift the output by
  exactly a factor of 2, easy to spot.
