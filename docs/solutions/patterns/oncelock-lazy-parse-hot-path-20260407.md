---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [rust, oncelock, performance, lazy-init, hot-path]
applies_when:
  - A parse or compile step is deterministic and input-independent
  - The result is needed on a hot path called many times per session
  - Global mutable state must be avoided for thread-safety reasons
related_components: [change_point_detection, cross_project_graph]
---

# OnceLock for Lazy Parse on Hot Paths

## Context

Several middens techniques parse the same structured constants (regex sets, keyword
tables, config DSL fragments) on every invocation. When these techniques run inside
the analyze pipeline — called per-session across thousands of sessions — repeated
parse cost becomes a silent tax. `lazy_static!` and `once_cell::Lazy` work but pull
in macro machinery or an extra crate; `std::sync::OnceLock` (stable since Rust 1.70)
is the smallest equivalent.

## Guidance

Wrap the deterministic parse in a function that returns a `&'static T` backed by a
module-level `OnceLock`:

```rust
use std::sync::OnceLock;

fn keyword_set() -> &'static Vec<&'static str> {
    static CELL: OnceLock<Vec<&'static str>> = OnceLock::new();
    CELL.get_or_init(|| {
        RAW_KEYWORDS.lines().filter(|l| !l.is_empty()).collect()
    })
}
```

Call sites become `for kw in keyword_set() { ... }` with no parse cost after the
first invocation, and no `unsafe`, no extra dependency, and no macro.

## Why This Matters

- **Cheap determinism**: parse-once semantics without reaching for `lazy_static`.
- **Thread-safety by construction**: `OnceLock` handles concurrent init; techniques
  called from rayon workers don't need extra guards.
- **Test-friendly**: the init closure runs inside `get_or_init`, so a test that
  imports the module pays parse cost once even across test functions.

## When to Apply

- Regex compilation reused across calls (pair with `regex::Regex` — always expensive
  to build).
- Keyword/stopword/category tables parsed from embedded `&'static str` blobs.
- Any `serde_yaml` / `serde_json` constants compiled into the binary via
  `include_str!`.

Do **not** apply to values that depend on runtime input (config paths, CLI flags),
and do not apply to values that must be reloadable during the process lifetime.

## Examples

Before (parses on every call, 1 allocation per session):

```rust
fn stopwords() -> Vec<String> {
    STOPWORDS_RAW.split('\n').map(String::from).collect()
}
```

After (parses once per process):

```rust
fn stopwords() -> &'static Vec<String> {
    static CELL: OnceLock<Vec<String>> = OnceLock::new();
    CELL.get_or_init(|| STOPWORDS_RAW.lines().map(String::from).collect())
}
```

Prefer returning borrowed slices (`&'static [T]`) over owned `Vec<T>` when the
caller only iterates — it removes the need for callers to clone.
