---
title: cross-project-graph times out due to per-project regex loop and nondeterministic project_lookup
date: 2026-04-13
category: performance-issues
module: middens/python/techniques
problem_type: performance_issue
component: tooling
symptoms:
  - "cross_project_graph.py times out at 900s on full corpus runs"
  - "project_lookup collision resolution varies between runs — same input, different output"
root_cause: logic_error
resolution_type: code_fix
severity: high
related_components:
  - testing_framework
tags: [cross-project-graph, python, performance, timeout, regex, nondeterminism, set-iteration, middens, python-bridge]
---

# `cross_project_graph` times out due to per-project regex loop and nondeterministic `project_lookup`

## Problem

`cross_project_graph.py` scanned each message once *per known project*, calling
`re.search(project_pattern, text)` in a nested loop. With 13k sessions, each
potentially containing dozens of messages, and hundreds of known projects, the
inner loop ran O(sessions × messages × projects) — enough to time out at 900s
on every full corpus run.

A secondary bug discovered during Codex review: `project_lookup` was built from
`known_projects`, a Python `set`. Set iteration order is hash-seed dependent
and changes every Python process. When two project names differed only in
capitalisation, the winner of the case-collision in `project_lookup` was
nondeterministic — same input corpus, different canonical project names, run to
run.

## Symptoms

- Technique times out at the 900s wall-clock limit on any corpus with hundreds
  of projects.
- Reports occasionally show a project under a different capitalisation than
  expected — and the discrepancy is not reproducible.

## What Didn't Work

- Pre-filtering sessions by message count to reduce work: the number of
  *projects* is the dominant factor in the inner loop, not the number of
  messages per session. Halving messages only halves the constant; the O(P)
  per-message factor remains.
- Sorting `known_projects` only for the regex alternation but leaving
  `project_lookup` built from the original set: the lookup dict inherits the
  nondeterminism from whichever iteration produced the last write for any
  colliding key.

## Solution

### Fix 1 — single compiled alternation pattern

Replace the per-project loop with one compiled regex whose alternation covers
all project names, sorted longest-first so the engine prefers longer matches
on ambiguous prefixes.

```python
# Before — O(sessions × messages × projects):
for src_project, session in sessions_with_project:
    for msg in session.get("messages", []):
        text = msg.get("text", "")
        for proj in known_projects:
            if re.search(re.escape(proj), text, re.IGNORECASE):
                # record edge ...

# After — O(sessions × messages), pattern compiled once:
sorted_projects = sorted(known_projects, key=lambda p: (-len(p), p.lower()))
combined_pattern = re.compile(
    r'\b(' + '|'.join(re.escape(p) for p in sorted_projects) + r')\b',
    re.IGNORECASE,
)

for src_project, session in sessions_with_project:
    for msg in session.get("messages", []):
        text = msg.get("text", "")
        for match in combined_pattern.finditer(text):
            dst_project = project_lookup.get(match.group(1).lower())
            # record edge ...
```

### Fix 2 — deterministic `project_lookup`

Build `project_lookup` from the deterministically sorted list, not the
original set. Reverse-iterate so that the alphabetically-first name is the
*last* writer for any case-collision key — meaning it wins in the final dict.

```python
# Before — nondeterministic: set iteration order is hash-seed dependent
project_lookup = {p.lower(): p for p in known_projects}

# After — deterministic: alphabetically-first name wins on case collision
sorted_projects = sorted(known_projects, key=lambda p: (-len(p), p.lower()))
project_lookup = {p.lower(): p for p in reversed(sorted_projects)}
```

With `sorted_projects` in longest-first order, `reversed(sorted_projects)` is
shortest-first. For two names that collide on their lowercase form (e.g.
`"Foo"` and `"foo"`), both will write to the same key; whichever is written
last wins. Since `reversed(sorted_projects)` processes the alphabetically-first
name last (it appears earliest in the sorted list, so last in the reversed
sequence), `"Foo"` beats `"foo"` deterministically.

## Why This Works

- **Fix 1**: A compiled alternation regex scans the text once and dispatches to
  whichever branch matches. Python's `re` uses an NFA which can exhibit
  worst-case exponential backtracking with ambiguous quantifiers — but because
  all project names are passed through `re.escape` (no special characters, no
  quantifiers), backtracking is not a concern here. In practice each `finditer`
  call is linear in message length. Sorting longest-first ensures that longer
  project names take priority over any shorter prefix they contain, which is the
  correct greedy behaviour for this use case.

- **Fix 2**: Python sets use a randomised hash seed per process (since Python
  3.3, PEP 456). Any dict comprehension built from direct set iteration will
  produce a different last-writer for colliding keys depending on the run. By
  sorting first and reversing, we make the collision resolution rule explicit
  and stable: alphabetically-first wins, every time.

## Prevention

- Never build a canonical lookup dict by iterating a Python `set` if two inputs
  could map to the same key. Always sort first and decide explicitly which value
  wins on collision.
- When an analysis technique needs to match a dynamic vocabulary (project names,
  user handles, tags) across large text bodies, build a single compiled
  alternation regex from the vocabulary instead of looping the vocabulary per
  message. The compilation cost is paid once; the scan cost per message is
  independent of vocabulary size.
- Add a smoke test that runs the technique twice on the same input and asserts
  byte-identical output — this catches nondeterminism before it reaches a
  report.

## Related

- `docs/solutions/patterns/deterministic-graph-tie-breaking-20260407.md` —
  same family of nondeterminism bug, but on the Rust side (HashMap iteration
  order); complements this Python-side fix
- Commit `867f57b` — both fixes, along with the PrefixSpan O(n²) fix
