---
module: middens
date: 2026-04-07
problem_type: logic_error
component: tooling
severity: medium
symptoms:
  - corpus_timeline reports the same calendar day multiple times in "peak days"
  - Top-N list includes duplicate rows when sessions span midnight
  - Counts per peak day disagree with downstream aggregates
root_cause: logic_error
resolution_type: code_fix
tags: [dedup, timeline, date-bucketing, aggregation]
---

# Deduplicate Before Ranking When Bucketing by Date

## Problem

`corpus_timeline` emits a "peak days" section: the top-N days ranked by session
count. The first pass bucketed sessions by `start_ts.date()` but then ranked the
raw (date, count) pairs without collapsing duplicate date keys that came from
different buckets (e.g., one per project in the cross-project variant). The same
calendar day appeared twice in the top-N, crowding out genuine peaks.

## Symptoms

- Top-5 peak days contains the same date twice.
- Total of peak-day counts exceeds the known per-day session count.
- Cosmetic but erodes trust — reviewers assume the underlying aggregation is
  broken, not just the presentation layer.

## What Didn't Work

- Sorting by date before ranking — doesn't collapse duplicates, just groups them
  adjacently.
- `dedup_by_key` on the sorted vec — only removes *adjacent* duplicates, so it
  works after sort-by-date but then loses the sum of counts for the collapsed
  rows.

## Solution

Use a single authoritative map keyed by date, accumulate counts into it, and only
then rank:

```rust
use std::collections::BTreeMap;

let mut by_day: BTreeMap<NaiveDate, u64> = BTreeMap::new();
for session in sessions {
    *by_day.entry(session.start_ts.date_naive()).or_default() += 1;
}

let mut ranked: Vec<_> = by_day.into_iter().collect();
ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
ranked.truncate(n);
```

`BTreeMap` also gives deterministic order on ties (pairs with the doc on
deterministic tie-breaking).

## Why This Works

- Aggregation and ranking are two steps, not one. Trying to rank an un-aggregated
  stream conflates the two and invites duplicate rows.
- The map structure enforces date uniqueness at the type level — you physically
  cannot emit the same date twice from a `BTreeMap<NaiveDate, _>`.

## Prevention

- Any "top-N by category" output should have an explicit aggregation step that
  produces a map keyed on the category, followed by an explicit ranking step.
  Collapse the two only when the input is already guaranteed unique on the key.
- Add a fixture with sessions that share a date across multiple projects/sources —
  the bug appears immediately.
- Audit other "top-N" emitters in the same technique suite for the same pattern.
