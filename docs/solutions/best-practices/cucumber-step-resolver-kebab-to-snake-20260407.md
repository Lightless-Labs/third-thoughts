---
module: middens
date: 2026-04-07
problem_type: best_practice
component: testing_framework
severity: medium
tags: [cucumber, rust, feature-flags, step-definitions, middens]
applies_when:
  - renaming .feature files or step-definition modules in middens
  - adding feature-flagged Cucumber scenarios
  - step files suddenly "not found" after a rename
---

# Cucumber step resolver maps kebab-case feature names to snake_case step files

## Context

In `middens/tests/features/` and `middens/tests/steps/`, the step resolver used by cucumber-rs expects step module filenames in `snake_case` even though the corresponding `.feature` files conventionally live under `kebab-case` names. When you rename a feature (e.g. `python-bridge.feature`), the matching step file must be `python_bridge.rs` — not `python-bridge.rs` — or the scenarios silently load zero steps and every Given/When/Then reports "step undefined."

## Guidance

When renaming or adding a Cucumber scenario set:

1. Name the `.feature` file in kebab-case: `tests/features/python-bridge.feature`
2. Name the step module in snake_case: `tests/steps/python_bridge.rs`
3. Register it in `tests/steps/mod.rs` (or the test binary's `main.rs`) using the snake_case identifier
4. If the scenario is gated on a Cargo feature, gate the step module with `#[cfg(feature = "python-bridge")]` at the top of the step file AND in `mod.rs`, or the compiler will drop the module but cucumber will still try to load the feature file and emit undefined-step noise

## Why This Matters

- cucumber-rs's file-based resolver uses Rust module naming rules (`snake_case`), not filesystem conventions.
- A kebab-case step file compiles (if renamed by hand) but is invisible to `mod.rs` without an explicit `#[path = "..."]` attribute — most authors miss this and blame cucumber.
- Feature-flag mismatch between step module and feature file creates the worst failure mode: green build, red scenarios, with no obvious link between cause and symptom.

## When to Apply

- Every time you add a new `.feature` file
- When renaming modules during a refactor
- When a PR review says "scenarios are undefined" but `cargo build` succeeds

## Examples

```rust
// middens/tests/steps/mod.rs
#[cfg(feature = "python-bridge")]
pub mod python_bridge;  // resolves tests/steps/python_bridge.rs
                         // matches tests/features/python-bridge.feature

pub mod classifier;
pub mod parser;
```

```gherkin
# tests/features/python-bridge.feature
@python-bridge
Feature: Python bridge technique execution
  ...
```

Run only the gated scenarios:

```bash
cargo test --manifest-path middens/Cargo.toml \
  --features python-bridge \
  --test cucumber -- @python-bridge
```
