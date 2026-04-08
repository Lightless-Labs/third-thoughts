---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: low
tags: [cargo, rustc, warnings, hygiene, middens]
applies_when:
  - cargo build emits unused-import or dead-code warnings
  - step-definition files accumulate helpers that become unused after a refactor
  - CI is about to gate on `-D warnings`
---

# Keep cargo build warning-free: unused imports and dead step-file code

## Context

Two recurring warning classes in middens:

1. **Unused `use` imports** — e.g. `use anyhow::Context;` left behind in `src/parser/claude_code.rs` after the error path that needed `.context("...")` was refactored away. Rustc warns but doesn't fail, so it accumulates until a `-D warnings` gate flips and a dozen show up at once.
2. **Dead helper functions in `tests/steps/*.rs`** — step files grow scratch helpers that become unused when scenarios are reworked. `#[allow(dead_code)]` is a smell; deleting is better.

## Guidance

- Run `cargo build --manifest-path middens/Cargo.toml 2>&1 | grep -E 'warning|unused'` after every non-trivial refactor.
- Delete unused imports immediately — don't `#[allow]` them. If a trait import is needed for method resolution only, use the `use Trait as _;` form to make intent explicit.
- For step files, delete dead helpers rather than gating them. Cucumber scenarios are the source of truth for what's exercised; helpers without a caller are dead weight.
- Gate CI on `-D warnings` once the baseline is clean:

```bash
RUSTFLAGS="-D warnings" cargo build --manifest-path middens/Cargo.toml
```

## Why This Matters

- Warnings in a growing codebase become background noise and mask new regressions.
- `use anyhow::Context;` specifically is easy to lose track of because it's a trait import used for method-call sugar (`.context(...)`), not a direct name — the compiler can't tell you "this trait was needed" unless you flip it to `Trait as _`.
- Dead step-file code is worse than dead production code: reviewers assume step files are exercised by `cargo test` and don't scrutinize them.
- CI gating on warnings prevents the ratchet from slipping.

## When to Apply

- After every error-path refactor (Context/anyhow usage tends to churn)
- Before every PR push
- When adding `-D warnings` to CI (clean the baseline first, then gate)

## Examples

Offending pattern seen this session:

```rust
// middens/src/parser/claude_code.rs — before
use anyhow::{Context, Result};

pub fn parse(path: &Path) -> Result<Session> {
    let raw = std::fs::read_to_string(path)?;   // no .context() call anymore
    ...
}
```

Fix:

```rust
use anyhow::Result;  // Context dropped — no caller remains
```

If Context is needed elsewhere in the module, leave it; if it's only imported for a method that's been removed, delete it.
