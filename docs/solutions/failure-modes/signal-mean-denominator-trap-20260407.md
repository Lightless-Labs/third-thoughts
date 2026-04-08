---
module: middens
date: 2026-04-07
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - Change-point scores spike on short sessions
  - Mean values drift when segments contain no qualifying messages
  - Silent divide behavior (0/0 → NaN or 0) depending on type
root_cause: logic_error
resolution_type: code_fix
tags: [statistics, denominators, change-point, mean, filtering]
related_components: [change_point_detection, user_signal_analysis]
---

# The Signal-Mean Denominator Trap

## Problem

When computing a mean-over-time signal for change-point detection, the denominator
must be the count of *qualifying* observations in each window, not the total window
length. Using the wrong denominator skews the signal, inflates change-point scores
on short or sparse sessions, and produces non-reproducible test output near segment
boundaries.

## Symptoms

- Change-point scores disproportionately high on sessions with few messages.
- Windows containing zero qualifying messages produce `0.0` instead of a skipped
  sample, pulling the rolling mean downward.
- PR reviewers flag "signal shape doesn't match description" on
  `change_point_detection`.

## What Didn't Work

- Scaling the signal by `window_len` after the fact — papers over the bug without
  fixing it, and still produces `NaN` on empty windows.
- Clamping to 0 when the filtered count is 0 — loses the "no data" signal, which
  is different from "data averaged to zero".

## Solution

Track two parallel counters inside each window: `numerator_sum` and
`matching_count`. Only divide by `matching_count`, and treat empty windows as
absent (skip the sample, propagate `None`, or interpolate from neighbours — but
never divide by the window width).

```rust
let mut sum = 0.0;
let mut n = 0usize;
for msg in window {
    if let Some(v) = qualifies(msg) {
        sum += v;
        n += 1;
    }
}
match n {
    0 => None,
    _ => Some(sum / n as f64),
}
```

A related fix applied in the same round: `change_point_detection` was reusing an
assistant-message context variable across iterations without resetting it. Stale
context from earlier messages bled into later windows. The fix was to
scope the context binding inside the loop body so each iteration starts fresh.

## Why This Works

- `n` is the true denominator for a mean — the window length is the sample rate,
  not the sample count.
- Propagating `None` for empty windows lets downstream segmentation distinguish
  "flat signal" from "no signal", which matters for change-point algorithms that
  treat gaps as breakpoints.
- Scoping mutable context inside the loop kills cross-iteration contamination at
  the language level — easier to reason about than a manual reset at the top of
  every branch.

## Prevention

- Any `sum / count` expression should have `count` constructed from the same
  filter predicate that built `sum`. If the two counters diverge, the code is
  almost certainly wrong.
- Add a regression test with a fixture that has one empty window — it catches
  both the denominator bug and the context-reset bug in a single assertion.
- Prefer `Iterator::filter(...).map(...).sum()` with an explicit `.count()` on the
  same filtered iterator — harder to get wrong than manual counters.
- When a loop mutates a "current context" variable, scope it inside the iteration
  body (`let mut ctx = ...;` per iteration) rather than hoisting it.
