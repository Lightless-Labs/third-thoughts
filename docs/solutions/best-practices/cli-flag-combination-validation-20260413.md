---
title: "Validate flag combinations at parse time, not individually"
date: 2026-04-13
category: best-practices
module: middens-cli
problem_type: best_practice
component: cli_argument_parsing
severity: high
applies_when:
  - "A CLI flag only makes sense alongside another flag"
  - "Adding dependent or paired flags to a clap-based CLI"
  - "A modifier flag (--force, --dry-run, --override) needs a primary flag to act on"
tags: [rust, clap, cli, argument-validation, fail-fast, paired-flags]
---

# Validate Flag Combinations at Parse Time, Not Individually

## Context

Middens `analyze` command grew a `--force` flag to bypass the floor/ceiling clamp on `--timeout`. When `--force` was accepted without `--timeout`, it was silently meaningless — the timeout was still computed from the session count formula, and `--force` had no effect. No warning, no error, just a quietly ignored flag.

Discovered alongside a related bug: `resolve_timeout()` was called before `needs_python` was computed, so `--no-python --timeout 30` still hit the 60 s floor because the function didn't know Python was disabled. Both bugs stem from the same root cause: individual flag values were validated, but flag *combinations* were not.

Commit: `867f57b`. Files: `middens/src/main.rs`, `middens/src/pipeline.rs`.

## Guidance

### Reject dependent flags without their required partner

```rust
// Bad: --force is silently ignored when --timeout is absent
// Good: reject the combination loudly at parse time
if force && timeout.is_none() {
    anyhow::bail!(
        "--force only applies to --timeout; pass --timeout <seconds> alongside it.\n\
         Example: middens analyze --timeout 120 --force corpus/"
    );
}
```

The error message should include (a) what was wrong, (b) what the expected form is, (c) a concrete example.

### Don't compute derived values until their preconditions are met

```rust
// Bad: resolve_timeout() called unconditionally, hits floor even for --no-python
let timeout = resolve_timeout(session_count, explicit_timeout, force);
// ... later ...
let needs_python = techniques.iter().any(|t| t.is_python());

// Good: compute needs_python first, then decide whether timeout matters
let needs_python = techniques.iter().any(|t| t.is_python());
let timeout = if needs_python {
    resolve_timeout(session_count, explicit_timeout, force)
} else {
    None
};
```

### General rule

A flag that only makes sense alongside another flag should be rejected as a pair at parse time — not silently ignored, not coerced into a best-guess default. If the combination is invalid, say so before any computation happens.

This applies to any CLI that takes paired or dependent flags: `--output-format` without `--output`, `--retry-count` without `--retry`, `--model-override` without `--model`, and so on.

## Why This Matters

Silent acceptance of nonsensical flag combinations hides bugs. The user sees no error, assumes the flag did something, and either files a bug report six months later or (worse) draws the wrong conclusion from the output. Loud rejection at parse time costs nothing and prevents both outcomes.

Per the project's fail-fast convention: never guess user intent. When a flag's value doesn't match the expected structure — or when it's meaningless without a companion flag — reject loudly with a clear message. Do not silently coerce or ignore.
