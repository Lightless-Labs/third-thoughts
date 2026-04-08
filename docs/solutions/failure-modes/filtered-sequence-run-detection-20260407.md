---
module: middens
date: 2026-04-07
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - Escalation runs detected across unrelated message pairs
  - Run length counted in mixed-role sequences instead of consecutive user turns
  - False positives on assistant-heavy transcripts
root_cause: logic_error
resolution_type: code_fix
tags: [sequence-analysis, filtering, runs, user-signal, rust]
---

# Run Detection Must Operate on the Filtered Sequence

## Problem

`user_signal_analysis` counts escalation runs — consecutive user messages showing
rising intensity. The first implementation iterated the full message sequence and
checked "is this a user message?" inside the run-tracking loop, incrementing the
run counter whenever the *current* user message satisfied the condition. That
counted non-consecutive user messages as consecutive, because intervening
assistant messages were silently skipped without breaking the run.

## Symptoms

- Runs of length 5 reported on sessions where the user only escalated twice in a
  row (with assistant replies interleaved).
- Review feedback: "escalation runs don't match the manually-counted transcripts".
- Fix produced no golden diff at first — because the goldens were computed from
  the buggy baseline.

## What Didn't Work

- Adding an "is previous message a user" check to the run increment — fragile and
  duplicates the filter logic in two places.
- Resetting the run counter on every assistant message — correct behaviour, but
  still requires the outer loop to understand the filter, mixing concerns.

## Solution

**Filter first, iterate second.** Project the message sequence onto the role you
care about, then run the sequential logic on the projection:

```rust
let user_msgs: Vec<&Message> = session
    .messages
    .iter()
    .filter(|m| m.role == Role::User)
    .collect();

let mut run = 0usize;
let mut best = 0usize;
let mut prev_score = None;
for msg in user_msgs {
    let score = intensity(msg);
    if prev_score.map_or(false, |p| score > p) {
        run += 1;
        best = best.max(run);
    } else {
        run = 1;
    }
    prev_score = Some(score);
}
```

The filter step makes "consecutive" mean what it looks like in the code.

## Why This Works

- The sequential invariant (`previous element is the element immediately before
  the current one in the relevant order`) is restored by construction.
- The filter predicate lives in one place instead of being smeared across the loop
  body, so future changes (e.g., "also count tool-result follow-ups") only touch
  the projection.
- Easier to test — the projection function can be unit-tested independently.

## Prevention

- Any "consecutive runs of X" logic should be phrased as *filter-then-iterate*,
  never *iterate-and-conditional-increment*. This is the sequence-analysis
  equivalent of "don't mutate while iterating".
- Regenerate goldens deliberately after a logic fix — diff the old and new
  fixtures and justify each change in the commit message.
- Add a fixture where the user alternates with the assistant but never escalates
  twice in a row — correct answer is run length 1, and the old bug reports the
  total user-message count.
