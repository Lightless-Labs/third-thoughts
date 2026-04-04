---
title: "Cucumber-rs v0.22 setup and pitfalls for Rust BDD testing"
date: 2026-04-01
category: best-practices
module: middens-testing
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "Setting up Cucumber/Gherkin BDD tests in a Rust project"
  - "Migrating from inline #[cfg(test)] to Cucumber scenarios"
tags: [cucumber-rs, gherkin, bdd, rust, testing, harness]
---

# Cucumber-rs v0.22 Setup and Pitfalls for Rust BDD Testing

## Context

Migrating 86 inline Rust tests to 178 Cucumber scenarios for the middens CLI. Several non-obvious pitfalls were discovered during the migration, with the worst causing a 36% test failure rate (64/178 scenarios) due to thread-local state management.

## Guidance

### 1. Cargo.toml configuration

Add `cucumber` and `futures` as dev-dependencies, and declare a test binary with `harness = false` so Cucumber controls the test lifecycle instead of libtest:

```toml
[dev-dependencies]
cucumber = "0.22"
futures = "0.3"

[[test]]
name = "cucumber"
harness = false
```

The `harness = false` is mandatory. Without it, Cargo's built-in test harness will try to run the binary as a normal `#[test]` suite and find zero tests.

### 2. Runner: `run_and_exit()`, not `run()`

The test binary's `main()` must use `run_and_exit()`:

```rust
fn main() {
    futures::executor::block_on(
        MiddensWorld::cucumber()
            .fail_on_skipped()
            .run_and_exit("tests/features"),
    );
}
```

`run()` returns a `Cucumber` value with results but does NOT set a non-zero exit code on failure. CI will report green even when scenarios fail. `run_and_exit()` calls `std::process::exit(1)` on any failure. Also chain `.fail_on_skipped()` to catch unimplemented steps early rather than silently passing them.

### 3. World struct: per-scenario mutable state

The `World` struct is constructed fresh for every scenario. Store all mutable state here:

```rust
#[derive(Debug, World)]
#[world(init = Self::new)]
pub struct MiddensWorld {
    pub sessions: Vec<Session>,
    pub technique_result: Option<TechniqueResult>,
    pub cli_output: String,
    pub error: Option<String>,
    pub temp_dir: Option<TempDir>,
    // ... all scenario state lives here
}

impl MiddensWorld {
    fn new() -> Self {
        Self {
            sessions: Vec::new(),
            technique_result: None,
            cli_output: String::new(),
            error: None,
            temp_dir: None,
        }
    }
}
```

NEVER use `thread_local!` or global `static`/`lazy_static` for test state. Cucumber-rs runs scenarios concurrently across threads. Thread-local state leaks between scenarios that happen to share a thread, producing intermittent failures that only manifest under concurrent execution. This was the root cause of 50+ test failures (36% failure rate) in the initial migration.

### 4. Step matching: `expr` vs `regex`

Use `expr = "..."` (Cucumber Expressions) for simple patterns:

```rust
#[given(expr = "a session with {int} messages")]
fn session_with_n_messages(world: &mut MiddensWorld, count: i32) { ... }
```

Cucumber Expressions support `{int}`, `{float}`, `{string}`, and `{word}` placeholders. However, they cannot represent literal brackets `[]`, braces `{}`, or other special characters. For patterns that include these, use `regex = r#"..."#`:

```rust
#[given(regex = r#"^a finding "([^"]*)" with array value \[1,2,3\] described as "([^"]*)"$"#)]
fn finding_with_array(world: &mut MiddensWorld, label: String, desc: String) { ... }
```

### 5. Step type strictness

In cucumber-rs, `#[given]` only matches `Given` steps, `#[when]` only matches `When` steps, and `#[then]` only matches `Then` steps. This is stricter than reference Cucumber (Ruby/Java), where `Given`/`When`/`Then` annotations are interchangeable and `And`/`But` inherit the preceding keyword. If a step appears under multiple keywords, it needs separate registrations or should be refactored.

### 6. Fixture paths

Use `env!("CARGO_MANIFEST_DIR")` to resolve paths relative to the crate root. This is evaluated at compile time and works regardless of the working directory at runtime:

```rust
let fixture = format!("{}/tests/fixtures/sample.jsonl", env!("CARGO_MANIFEST_DIR"));
```

Do not use `std::env::current_dir()` or relative paths. The working directory during test execution varies by IDE, CI runner, and invocation method.

### 7. MSRV requirement

Cucumber 0.22 requires Rust 1.88+ (edition 2024). Ensure `rust-version = "1.88"` is set in Cargo.toml and that CI toolchains are updated accordingly. Earlier editions will produce confusing compile errors in the proc macro expansion.

### 8. Import registration for proc macros

Step definition modules must be explicitly `use`d in the test binary for the proc macros to register their steps with the Cucumber runtime. Without the import, the steps exist in the compiled code but are never linked into the runner, and all scenarios using those steps will be skipped:

```rust
// In tests/cucumber.rs
mod steps;

// Each module MUST be imported — the proc macros register on import
#[allow(unused_imports)]
use steps::parser;
#[allow(unused_imports)]
use steps::classifier;
#[allow(unused_imports)]
use steps::output;
```

The `#[allow(unused_imports)]` suppresses warnings since the imports are used only for their registration side effects, not for any symbols.

## Why This Matters

Thread-local state caused 50+ test failures (36% failure rate) that only appeared when running the full suite, never in isolation. `run()` vs `run_and_exit()` silently swallows failures, meaning CI can pass while tests are actually broken. These are the kind of integration pitfalls that waste hours because the symptoms are far removed from the cause.

## When to Apply

- First-time setup of Cucumber-rs in any Rust project
- Migrating from `#[cfg(test)]` unit tests to BDD scenarios
- Debugging intermittent Cucumber test failures (check for thread-local state)
- CI reporting green when local runs show failures (check `run_and_exit` vs `run`)

## Examples

Complete minimal setup:

**`Cargo.toml`**:
```toml
[dev-dependencies]
cucumber = "0.22"
futures = "0.3"

[[test]]
name = "cucumber"
harness = false
```

**`tests/cucumber.rs`**:
```rust
mod steps;

use cucumber::World;
use steps::world::MyWorld;

#[allow(unused_imports)]
use steps::my_feature;

fn main() {
    futures::executor::block_on(
        MyWorld::cucumber()
            .fail_on_skipped()
            .run_and_exit("tests/features"),
    );
}
```

**`tests/steps/world.rs`**:
```rust
use cucumber::World;

#[derive(Debug, World)]
#[world(init = Self::new)]
pub struct MyWorld {
    pub result: Option<String>,
}

impl MyWorld {
    fn new() -> Self {
        Self { result: None }
    }
}
```

**Regex mode for complex patterns**:
```rust
#[then(regex = r#"^the output should contain \{"key":"([^"]*)"\}$"#)]
fn output_contains_object(world: &mut MyWorld, key: String) {
    // regex captures are positional arguments after world
}
```

## Related

- Implementation: `middens/tests/cucumber.rs`, `middens/tests/steps/world.rs`
- Cucumber-rs docs: https://cucumber-rs.github.io/cucumber/main/
- Cargo.toml config: `middens/Cargo.toml`
