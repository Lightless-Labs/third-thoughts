---
title: "Python bridge: dynamic timeout with floor/ceiling and --force override"
status: todo
priority: P2
issue_id: null
tags: [python-bridge, scaling, cli, techniques]
source: session-2026-04-11
---

## Problem

The Python bridge uses a fixed 900s timeout for all techniques regardless of corpus size. This is simultaneously too generous for small corpora (masks runaway scripts) and too tight for legitimate heavy techniques on large ones.

## Design

Compute a per-run timeout from corpus characteristics:

```
computed = base_seconds × log(session_count) × f(median_session_bytes)
timeout  = clamp(computed, floor=60s, ceiling=1800s)
```

Going outside the floor or ceiling requires `--force`. The error messages should say exactly why and what to pass:

- Below floor: `"computed timeout is 8s for 12 sessions — below the 60s floor to guard against accidental short-circuits; pass --force to override"`
- Above ceiling: `"computed timeout for 13,497 sessions is 2,100s — exceeds the 1,800s ceiling; pass --force to run anyway"`

`--force` overrides both directions with a single flag.

## Scope

- `PipelineConfig`: add `force: bool`; change `timeout_seconds: u64` to an enum (`Auto` | `Explicit(u64)`)
- `pipeline.rs`: compute timeout before constructing Python techniques; emit the clamped-or-forced value in the run summary
- `all_techniques_with_python()` / `python_techniques()`: take the computed timeout instead of a hardcoded constant
- CLI (`analyze` subcommand): add `--force` flag; `--timeout` still accepted but subject to floor/ceiling unless `--force`
- Manifest: record the computed timeout and whether `--force` was used

## Sequencing

After O(n²) sampling (`todos/python-techniques-onk2-sampling.md`). `prefixspan-mining` and `cross-project-graph` will hit the ceiling on every full-corpus run until sampling is in place — dynamic timeout alone doesn't fix them, it just makes the guard rail explicit.

## Acceptance criteria

- Small corpus (< 100 sessions): timeout auto-computes well below ceiling, no --force needed
- Full corpus (13k sessions): timeout auto-computes within floor/ceiling range
- Explicit `--timeout` below floor without `--force`: rejected with clear message
- Explicit `--timeout` above ceiling without `--force`: rejected with clear message
- `--force` bypasses both checks; manifested in run output
- Existing 333/333 Cucumber scenarios still pass
