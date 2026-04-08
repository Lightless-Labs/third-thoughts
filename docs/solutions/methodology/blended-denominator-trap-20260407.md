---
module: analysis
date: 2026-04-07
problem_type: best_practice
component: documentation
severity: high
tags: [denominators, tool-rate, rates, stratification, anti-pattern]
applies_when:
  - computing a "per session" or "per unit" rate on a heterogeneous corpus
  - a rate changes dramatically between corpus cuts
  - reviewing an older finding that was reported as a single scalar
---

# The blended-denominator trap: never average rates across incompatible populations

## Context

The Batch 4 investigation reported a tool-rate drop from 572/session to
8.9/session and spent real time trying to explain the delta as a
behavioral regression. There was no regression. The 8.9 number was the
arithmetic result of averaging the interactive+subagent cohort
(~572/session) with the autonomous Boucle cohort (0/session) after
weighting by population share in the W10–W12 window. The "drop" was an
artifact of the mixing ratio shifting, not of any agent's behavior
changing.

This is the same failure mode as the 85.5 → 100 risk-suppression
reframe, expressed on a different axis. The pattern is general enough
that it deserves its own name and its own prevention rule.

## Guidance

Any rate `X / N` computed over a corpus that spans multiple strata is
only meaningful if `X` and `N` refer to the same population. In
practice this means:

1. **Never report a single blended rate** when the strata have
   structurally different capabilities for producing `X`. Report the
   rate per stratum, plus the stratum weights, and let the reader
   compose them if they want an aggregate.
2. **Refuse to compare blended rates across time windows** when the
   stratum mix is drifting. The comparison is measuring the mix
   change, not the behavior change.
3. **If an aggregate must be reported**, label it "population-weighted
   mean across strata S₁…Sₙ at mix ratio r₁…rₙ as of <date>" — not a
   finding. It has a shelf life of exactly one rerun.

The test for whether you are in the trap: ask whether doubling the
size of one stratum would change the reported number without any
underlying behavior changing. If yes, you have a blended denominator
and the number is not a finding.

## Why This Matters

Blended denominators are seductive because they look like scalar
findings and fit neatly into tables and commit messages. But they
encode an implicit claim — "these sub-populations are comparable on
this axis" — that almost never survives scrutiny in this corpus. The
cost of catching the mistake late is high: any downstream analysis
built on the blended number inherits the artifact, and retractions
ripple.

The 572 → 8.9 framing spent a week of investigation time on a
phenomenon that did not exist. The generalized rule is cheap: any
rate that is not stratum-scoped is treated as provisional until
proven otherwise.

## When to Apply

- Reporting tool-use rates, correction rates, error rates, token
  rates, or any other per-session aggregate.
- Reviewing any finding in `docs/HANDOFF.md` or
  `experiments/*/` that is expressed as a single number.
- Writing summary tables in reports where scope is usually
  suppressed for readability — the table headers must still encode
  the scope.

## Examples

**Wrong:**

> Tool rate dropped from 572 → 8.9 in W10–W12. Investigating.

**Right:**

> Tool rate by stratum, W10–W12:
>   session_type=interactive   572.1/session  (N=…)
>   session_type=subagent      568.7/session  (N=…)
>   session_type=autonomous      0.0/session  (N=1,820)
> No behavioral change detected in interactive or subagent cohorts.
> The W10–W12 "drop" is a mix-shift artifact from the autonomous
> cohort entering the corpus.

Related:
- `docs/solutions/methodology/autonomous-stratum-boucle-w10-w12-20260407.md`
- `docs/solutions/methodology/visible-only-denominator-risk-suppression-20260407.md`
- `docs/solutions/methodology/compound-scoping-rule-4-axis-stratification-20260407.md`
