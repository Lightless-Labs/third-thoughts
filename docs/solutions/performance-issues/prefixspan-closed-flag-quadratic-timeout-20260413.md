---
title: PrefixSpan closed=True triggers O(n²) filtering and times out on large corpora
date: 2026-04-13
category: performance-issues
module: middens/python/techniques
problem_type: performance_issue
component: tooling
symptoms:
  - "prefixspan_mining.py times out at 900s on every full-corpus run (13k sequences)"
  - "Zero output returned — timeout masked pre-existing row-shape and index bugs"
  - "No error message — subprocess just dies on the wall-clock limit"
root_cause: wrong_api
resolution_type: code_fix
severity: high
related_components:
  - testing_framework
tags: [prefixspan, python, performance, timeout, closed-patterns, sequential-patterns, middens, python-bridge]
---

# PrefixSpan `closed=True` triggers O(n²) filtering and times out on large corpora

## Problem

`prefixspan_mining.py` called `ps.topk(200, closed=True)`. On a 13k-sequence
corpus the `closed=True` flag triggers a post-mining closed-pattern filter that
compares every candidate against every other candidate — O(n²) in the number
of frequent subsequences. At 13k sequences the filter never completed within
the 900s subprocess timeout. The technique returned zero output on every full
corpus run.

Making it worse: zero output silenced two pre-existing bugs (a row-shape
mismatch and an off-by-index in cohort building) that had always been lurking
but had never had output to expose them.

## Symptoms

- Subprocess times out at exactly the wall-clock limit every time; no partial
  results.
- Technique shows zero patterns in the report even though the corpus is large
  enough that patterns clearly exist.
- No Python error or traceback — the process just hits the ceiling and is killed.

## What Didn't Work

- Raising the timeout: the filter is genuinely O(n²) on the candidate set size,
  not a constant-factor issue. Doubling the timeout just doubled the wall time
  before the same kill.
- Reducing `topk(k)` to a lower k: `closed=True` filtering compares across the
  *full* frequent-pattern lattice before selecting top-k, so the k parameter
  does not bound the intermediate work.

## Solution

### Fix 1 — drop `closed=True`

`closed=True` is rarely necessary in practice. The top-200 by support already
gives a compact, interpretable result set without the quadratic filter.

```python
# Before (times out on corpora with thousands of sequences):
all_patterns = ps.topk(200, closed=True)

# After:
all_patterns = ps.topk(200)
```

### Fix 2 — row-shape bug exposed by restoring output

With output flowing again, a pre-existing contract violation surfaced
immediately: table rows were dicts instead of the positional arrays required by
the Rust `DataTable` schema (see
`docs/solutions/integration-issues/python-rust-json-contract-gotchas-20260406.md`
§ "Table rows format mismatch").

```python
# Before (emits list-of-dicts, rejected by serde):
frequent_table.append({
    "pattern": " -> ".join(pattern),
    "length": len(pattern),
    "support": support,
    "support_pct": round(support_pct, 2),
})

# After (positional list matching columns order):
frequent_table.append([
    " -> ".join(pattern),
    len(pattern),
    support,
    round(support_pct, 2),
])
```

### Fix 3 — off-by-index in discriminative cohort building

`extract_tool_sequences(sessions)` silently skips sessions with no tool calls,
so `len(sequences) <= len(sessions)`. The cohort loop previously used
`enumerate(sessions)` and indexed into `sequences` with those same integers —
wrong whenever any no-tool-call sessions appear before a tool-call session in
the list (the `sequences` index drifts below the session index).

```python
# Before (session index used to index sequences — wrong when gaps exist):
for i, session in enumerate(sessions):
    if i >= len(sequences):
        break
    rate = get_correction_rate(session)
    seq = sequences[i]   # BUG: i is the session index, not the sequences index
    ...

# After (aligned single pass — no index arithmetic):
seq_idx = 0
for session in sessions:
    has_tools = any(
        isinstance(tc, dict) and tc.get("name")
        for msg in session.get("messages", []) if msg.get("role") == "Assistant"
        for tc in msg.get("tool_calls", [])
    )
    if not has_tools:
        continue
    if seq_idx >= len(sequences):
        break
    rate = get_correction_rate(session)
    seq = sequences[seq_idx]
    ...
    seq_idx += 1
```

## Why This Works

- **Fix 1**: `topk(k)` bounds the result set to at most k patterns by support
  rank, without the quadratic closed-pattern filter. For exploratory analysis
  the top-200 frequent patterns are already more than you can usefully read; the
  closed-pattern guarantee is a theoretical nicety that costs O(n²) in practice.

- **Fix 2**: Rust's `serde_json` deserializes `DataTable.rows` as
  `Vec<Vec<Value>>`. A dict (`{}`) is not a JSON array, so deserialization
  fails. The fix is to emit rows as positional lists whose element order matches
  `columns`.

- **Fix 3**: `extract_tool_sequences` is a filter — it only appends to
  `sequences` when a session has at least one named tool call. Any session
  without tool calls creates a gap between the session index and the sequences
  index. The aligned single-pass replicates the filter condition inline so the
  two cursors stay in sync without relying on index identity.

## Prevention

- Never pass `closed=True` to `ps.topk()` on corpora with more than a few
  hundred sequences. If closed patterns are genuinely required, benchmark the
  candidate count first; the filter cost scales with the *candidate count*, not
  the number of input sequences directly — but candidate count grows with corpus
  size, so they are correlated. On a 13k-sequence corpus the candidate set was
  large enough to make the filter non-terminating within 900s.
- Any time a helper function filters its input (skipping items rather than
  transforming them), do not assume that the original index is usable as an
  index into the helper's output. Either return an aligned structure, or iterate
  with a single pass that mirrors the same filter condition. A return type
  annotation of `List[List[str]]` on `extract_tool_sequences` would not have
  caught this bug, but a name like `tool_sequences_for_sessions_with_tools`
  makes the "some sessions are absent" semantics harder to forget.
- Zero output from a subprocess technique is not a clean success — treat it as
  a warning signal worth investigating even when the exit code is 0. A technique
  that always times out silently is indistinguishable from one that legitimately
  found nothing.

## Related

- `docs/solutions/integration-issues/python-scientific-library-api-quirks-20260406.md`
  — earlier PrefixSpan bug: `frequent()` → `topk(200, closed=True)` (the fix
  that introduced the `closed=True` which this doc now removes)
- `docs/solutions/integration-issues/python-rust-json-contract-gotchas-20260406.md`
  — full DataTable row-shape contract and other Python↔Rust serialization rules
- Commit `867f57b` — all three fixes together
