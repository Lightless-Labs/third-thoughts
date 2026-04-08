---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: low
tags: [cargo, rust, middens, workflow, monorepo]
applies_when:
  - running cargo commands from the third-thoughts repo root
  - agent sessions where cwd may reset between bash calls
  - scripting tests across multiple crates
---

# Invoke cargo with `--manifest-path` from repo root

## Context

Agent bash tools reset cwd between calls. `cd middens && cargo test` works interactively but fails in agent workflows where each command starts at the repo root (or wherever the session left off). Using absolute paths + `--manifest-path` is the portable form.

## Guidance

```bash
# Good — works from any cwd, no state leakage
cargo test --manifest-path /Users/thomas/Projects/lightless-labs/third-thoughts/middens/Cargo.toml
cargo build --release --manifest-path middens/Cargo.toml
cargo clippy --manifest-path middens/Cargo.toml -- -D warnings

# Fragile in agent contexts
cd middens && cargo test
```

For feature-flagged tests:

```bash
cargo test --manifest-path middens/Cargo.toml --features python-bridge -- echo
```

## Why This Matters

- Matches the CLAUDE.md convention that bash calls should use absolute paths because cwd resets between calls.
- Avoids "works on my machine" drift between human and agent sessions.
- Lets a single orchestrator fire parallel `cargo` invocations against different crates without `cd` races.
- `--manifest-path` is honored by every cargo subcommand (`test`, `build`, `clippy`, `fmt`, `run`, `check`).

## When to Apply

- Always in agent / CI scripts
- When chaining multiple cargo commands in one shell call against different crates
- When the user reports "I ran it and it failed but you said it passed" — usually cwd drift

## Examples

Parallel test + clippy + fmt check in a single Bash tool call:

```bash
cargo test    --manifest-path middens/Cargo.toml && \
cargo clippy  --manifest-path middens/Cargo.toml -- -D warnings && \
cargo fmt     --manifest-path middens/Cargo.toml -- --check
```
