---
title: "refactor: Rewrite tests using Cucumber/Gherkin BDD"
type: refactor
status: active
date: 2026-03-29
---

# refactor: Rewrite tests using Cucumber/Gherkin BDD

## Overview

Rewrite the middens CLI test suite from 86 inline `#[cfg(test)]` unit tests to BDD-style Cucumber tests with `.feature` files (Gherkin) and Rust step definitions using the `cucumber` crate (v0.22). Delivers as a dedicated PR on a feature branch.

## Problem Frame

The current tests are scattered across 13 modules as inline `#[cfg(test)]` blocks. While they pass (86 tests, 0 failures), they don't communicate *what* the system does in business-readable language. Cucumber/Gherkin features serve as living documentation that describes behavior from the user's perspective, making the test suite readable by non-Rust developers and aligning with the project's research-oriented audience.

## Requirements Trace

- R1. All 86 existing test scenarios must be preserved as Cucumber scenarios (no coverage regression)
- R2. `.feature` files use standard Gherkin syntax, organized by domain (parsers, classifiers, corpus, techniques, CLI)
- R3. Step definitions in Rust using the `cucumber` crate v0.22
- R4. `cargo test` continues to work — both cucumber tests and the 1 doc-test pass
- R5. Inline `#[cfg(test)]` modules are removed from source files after migration
- R6. Delivered as a PR on a dedicated feature branch, not committed to main

## Scope Boundaries

- The 1 doc-test in `parser::openclaw` stays as-is (doc-tests are not Cucumber candidates)
- No new test scenarios added — this is a 1:1 migration of existing coverage
- No changes to library or CLI code — only test infrastructure
- No CI/CD setup (no GitHub Actions yet)

## Context & Research

### Relevant Code and Patterns

- 86 tests across 13 modules, cataloged in detail during planning
- Common patterns: `session_with_tools()` / `make_session()` / `user_msg()` helpers for constructing test data
- Fixture files: `tests/fixtures/{claude_code,codex,openclaw}_sample.jsonl`
- `tempfile::TempDir` used for filesystem tests (discovery, manifest)

### External References

- `cucumber` crate v0.22.1 — MSRV 1.88, edition 2024
- Requires `harness = false` in `[[test]]` Cargo.toml stanza
- `World` struct holds per-scenario mutable state, freshly constructed per scenario
- `run_and_exit()` required (not `run()`) to get non-zero exit codes on failure
- `fail_on_skipped()` catches missing step implementations
- Steps are strict by type: `#[given]` only matches Given, etc.

## Key Technical Decisions

- **Single test binary, multiple feature files**: One `tests/cucumber.rs` binary with step definition modules organized by domain. Multiple `.feature` files under `tests/features/`. Rationale: keeps the runner simple, the crate is small enough that one binary is sufficient, and feature files provide the logical separation.
- **Sync runner with `futures::executor`**: No async code in middens, so `futures::executor::block_on` is lighter than pulling in `tokio`. Rationale: avoids adding a large async runtime dependency for purely synchronous test code.
- **World struct holds**: parsed sessions, technique results, CLI output, tempdir handles, and error state. One World type covers all domains. Rationale: simpler than multiple World types; the struct is just test state.
- **Step modules mirror source modules**: `steps/parser.rs`, `steps/classifier.rs`, `steps/corpus.rs`, `steps/techniques.rs`, `steps/cli.rs`. Rationale: 1:1 mapping makes it easy to find steps for a given feature.
- **Cucumber Expressions over regex**: Use `{word}`, `{int}`, `{float}`, `{string}` placeholders for readability. Fall back to regex only when expressions can't handle the pattern.
- **Remove inline tests after migration**: Each module's `#[cfg(test)]` block is deleted once its scenarios are verified in Cucumber. Rationale: no duplication; Cucumber is the single test authority.

## Open Questions

### Resolved During Planning

- **Can cucumber tests coexist with cargo test?** Yes — `[[test]] harness = false` makes cucumber a separate test binary. `cargo test` runs both it and doc-tests.
- **Does cucumber 0.22 work with edition 2024?** Yes — it requires it (MSRV 1.88).

### Deferred to Implementation

- **Exact step phrasing**: The precise Given/When/Then wording will be refined during implementation to balance readability and reusability
- **Whether some edge-case tests map better to Scenario Outlines**: Tests with multiple similar cases (e.g., path detection for 4 tools) may benefit from Examples tables — decide during implementation

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification.*

```text
middens/
  Cargo.toml                          # Add [dev-dependencies] cucumber, futures
                                      # Add [[test]] name="cucumber" harness=false
  tests/
    cucumber.rs                       # main() -> World::cucumber().run_and_exit("tests/features")
                                      #   mod steps;  (imports all step modules)
    steps/
      mod.rs                          # re-exports all step modules
      world.rs                        # World struct + Default impl
      parser.rs                       # Given/When/Then for parser scenarios
      classifier.rs                   # Steps for classifier scenarios
      corpus.rs                       # Steps for discovery + manifest
      techniques.rs                   # Steps for all 5 techniques
      cli.rs                          # Steps for parse/freeze/list-techniques commands
    features/
      parsers/
        claude_code.feature           # 11 scenarios
        codex.feature                 # 3 scenarios
        openclaw.feature              # 4 scenarios (minus doc-test)
        auto_detect.feature           # 7 scenarios
      classifiers/
        correction.feature            # 12 scenarios
        session_type.feature          # 7 scenarios
      corpus/
        discovery.feature             # 2 scenarios
        manifest.feature              # 2 scenarios
      techniques/
        markov.feature                # 6 scenarios
        entropy.feature               # 7 scenarios
        diversity.feature             # 7 scenarios
        burstiness.feature            # 9 scenarios
        correction_rate.feature       # 8 scenarios
        registry.feature              # 1 scenario
      cli/
        parse.feature                 # ~3 scenarios (from main.rs wiring)
        freeze.feature                # ~2 scenarios
        list_techniques.feature       # ~2 scenarios
  src/
    (all #[cfg(test)] modules removed)
```

## Implementation Units

- [ ] **Unit 1: Add cucumber dependency and test harness skeleton**

**Goal:** Set up the cucumber test infrastructure — Cargo.toml, World struct, empty runner

**Requirements:** R3, R4

**Dependencies:** None

**Files:**
- Modify: `middens/Cargo.toml`
- Create: `middens/tests/cucumber.rs`
- Create: `middens/tests/steps/mod.rs`
- Create: `middens/tests/steps/world.rs`

**Approach:**
- Add `cucumber = "0.22"` and `futures = "0.3"` to `[dev-dependencies]`
- Add `[[test]] name = "cucumber" harness = false`
- World struct with fields for: sessions (`Vec<Session>`), technique_result (`Option<TechniqueResult>`), cli_output (`String`), cli_exit_code (`Option<i32>`), temp_dir (`Option<TempDir>`), error (`Option<String>`), detected_format (`Option<SourceTool>`)
- Runner uses `futures::executor::block_on` with `fail_on_skipped()` and `run_and_exit()`
- Create one empty `.feature` file to verify the harness runs

**Test scenarios:**
- Happy path: `cargo test --test cucumber` runs and exits cleanly with 0 scenarios

**Verification:**
- `cargo test --test cucumber` succeeds
- `cargo test` still runs the 1 doc-test

---

- [ ] **Unit 2: Migrate parser tests to Cucumber**

**Goal:** Convert all 25 parser tests (claude_code: 11, codex: 3, openclaw: 4, auto_detect: 7) to .feature files with step definitions

**Requirements:** R1, R2, R5

**Dependencies:** Unit 1

**Files:**
- Create: `middens/tests/features/parsers/claude_code.feature`
- Create: `middens/tests/features/parsers/codex.feature`
- Create: `middens/tests/features/parsers/openclaw.feature`
- Create: `middens/tests/features/parsers/auto_detect.feature`
- Create: `middens/tests/steps/parser.rs`
- Modify: `middens/tests/steps/mod.rs`
- Modify: `middens/src/parser/claude_code.rs` (remove `#[cfg(test)]` module)
- Modify: `middens/src/parser/codex.rs` (remove `#[cfg(test)]` module)
- Modify: `middens/src/parser/openclaw.rs` (remove `#[cfg(test)]` module, keep doc-test)
- Modify: `middens/src/parser/auto_detect.rs` (remove `#[cfg(test)]` module)

**Approach:**
- Shared steps: "Given a session file {string}" (loads fixture), "When I parse the file" (calls parse_auto), "Then the session count should be {int}"
- Claude Code scenarios use the existing fixture at `tests/fixtures/claude_code_sample.jsonl`
- Auto-detect scenarios use tempfile for content-based detection and hardcoded paths for path-based
- Codex/OpenClaw scenarios preserve the "skip if fixture absent" behavior via `@skip_if_no_fixture` tag

**Test scenarios:**
- Happy path: All 25 parser scenarios pass in Cucumber
- Edge case: Missing fixture files don't cause hard failures (tagged skip)

**Verification:**
- `cargo test --test cucumber` passes all parser scenarios
- Inline `#[cfg(test)]` blocks removed from all 4 parser source files

---

- [ ] **Unit 3: Migrate classifier tests to Cucumber**

**Goal:** Convert all 19 classifier tests (correction: 12, session_type: 7)

**Requirements:** R1, R2, R5

**Dependencies:** Unit 1

**Files:**
- Create: `middens/tests/features/classifiers/correction.feature`
- Create: `middens/tests/features/classifiers/session_type.feature`
- Create: `middens/tests/steps/classifier.rs`
- Modify: `middens/tests/steps/mod.rs`
- Modify: `middens/src/classifier/correction.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/classifier/session_type.rs` (remove `#[cfg(test)]`)

**Approach:**
- Correction scenarios: "Given a user message {string}" / "When I classify the message" / "Then it should be classified as {word}"
- Session type scenarios: "Given a session with path {string}" / "Given a session with messages classified as {word}" / "Then the session type should be {word}"
- Use Scenario Outlines with Examples tables for the 12 correction pattern tests (many follow the same pattern with different inputs)

**Test scenarios:**
- Happy path: All 19 classifier scenarios pass
- Integration: Correction classifier pipeline (structural → system tags → lexical → positional → fallback) is exercised

**Verification:**
- `cargo test --test cucumber` passes all classifier scenarios
- Inline tests removed from both classifier source files

---

- [ ] **Unit 4: Migrate corpus tests to Cucumber**

**Goal:** Convert all 4 corpus tests (discovery: 2, manifest: 2)

**Requirements:** R1, R2, R5

**Dependencies:** Unit 1

**Files:**
- Create: `middens/tests/features/corpus/discovery.feature`
- Create: `middens/tests/features/corpus/manifest.feature`
- Create: `middens/tests/steps/corpus.rs`
- Modify: `middens/tests/steps/mod.rs`
- Modify: `middens/src/corpus/discovery.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/corpus/manifest.rs` (remove `#[cfg(test)]`)

**Approach:**
- Discovery steps use World's temp_dir field for filesystem setup
- "Given a directory with {int} JSONL files" creates temp structure
- "When I discover sessions in the directory" calls discover_sessions
- Manifest steps verify SHA-256 hashing and file recording

**Test scenarios:**
- Happy path: Discovery finds nested JSONL files, manifest records them with checksums
- Edge case: Non-existent directory returns empty result

**Verification:**
- `cargo test --test cucumber` passes all corpus scenarios
- Inline tests removed from both corpus source files

---

- [ ] **Unit 5: Migrate technique tests to Cucumber**

**Goal:** Convert all 38 technique tests (markov: 6, entropy: 7, diversity: 7, burstiness: 9, correction_rate: 8, registry: 1)

**Requirements:** R1, R2, R5

**Dependencies:** Unit 1

**Files:**
- Create: `middens/tests/features/techniques/markov.feature`
- Create: `middens/tests/features/techniques/entropy.feature`
- Create: `middens/tests/features/techniques/diversity.feature`
- Create: `middens/tests/features/techniques/burstiness.feature`
- Create: `middens/tests/features/techniques/correction_rate.feature`
- Create: `middens/tests/features/techniques/registry.feature`
- Create: `middens/tests/steps/techniques.rs`
- Modify: `middens/tests/steps/mod.rs`
- Modify: `middens/src/techniques/markov.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/techniques/entropy.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/techniques/diversity.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/techniques/burstiness.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/techniques/correction_rate.rs` (remove `#[cfg(test)]`)
- Modify: `middens/src/techniques/mod.rs` (remove `#[cfg(test)]`)

**Approach:**
- Shared steps: "Given a session with tools {string}" (comma-separated tool list), "When I run the {word} technique", "Then the result should contain finding {string}"
- Technique-specific steps for detailed assertions (transition matrix values, entropy thresholds, diversity indices)
- Correction rate needs steps for message classification setup: "Given a session with {int} corrections in {int} user messages"
- Use Scenario Outlines for burstiness edge cases (periodic, clustered, sparse)

**Test scenarios:**
- Happy path: All 38 technique scenarios pass
- Edge case: Empty sessions, single-tool sessions, zero-data cases all handled

**Verification:**
- `cargo test --test cucumber` passes all technique scenarios
- Inline tests removed from all 6 technique source files

---

- [ ] **Unit 6: Add CLI command scenarios**

**Goal:** Add Cucumber scenarios for the wired CLI commands (parse, freeze, list-techniques)

**Requirements:** R1, R2

**Dependencies:** Units 1, 2

**Files:**
- Create: `middens/tests/features/cli/parse.feature`
- Create: `middens/tests/features/cli/freeze.feature`
- Create: `middens/tests/features/cli/list_techniques.feature`
- Create: `middens/tests/steps/cli.rs`
- Modify: `middens/tests/steps/mod.rs`

**Approach:**
- CLI steps build and invoke the middens binary via `std::process::Command` or call library functions directly
- "When I run middens parse {string}" / "Then the output should be valid JSON" / "Then the output should contain {int} sessions"
- Freeze scenarios verify manifest file creation
- List-techniques verifies tabular output with all 5 techniques

**Test scenarios:**
- Happy path: `parse` on Claude Code fixture outputs valid JSON with 1 session
- Happy path: `freeze` on fixtures dir creates manifest with 3 entries
- Happy path: `list-techniques` shows 5 registered techniques
- Error path: `parse` with unsupported format exits with error
- Edge case: `parse` on unrecognized file outputs empty array

**Verification:**
- `cargo test --test cucumber` passes all CLI scenarios

---

- [ ] **Unit 7: Final cleanup and PR**

**Goal:** Remove all remaining inline test code, verify full suite, create PR

**Requirements:** R4, R5, R6

**Dependencies:** Units 2-6

**Files:**
- Verify: All `#[cfg(test)]` modules removed from `src/`
- Verify: `cargo test` runs cucumber + doc-test, no inline tests remain

**Approach:**
- Grep for remaining `#[cfg(test)]` in `src/` — should find zero matches
- Run `cargo test` — should show cucumber scenarios + 1 doc-test passing
- Create feature branch, commit, push, open PR

**Test scenarios:**
- Happy path: `cargo test` succeeds with only cucumber + doc-test output
- Edge case: No `#[cfg(test)]` blocks remain in any `src/` file

**Verification:**
- `grep -r '#\[cfg(test)\]' src/` returns zero matches
- `cargo test` passes all scenarios
- PR created on GitHub

## Risks & Dependencies

- **MSRV 1.88 required**: cucumber 0.22 requires Rust 1.88+. The project uses edition 2024 so this should already be satisfied, but verify the toolchain version
- **Test count may differ**: Cucumber counts scenarios, not assertions. The final scenario count may not be exactly 86 if some inline tests map to Scenario Outline rows
- **Fixture path resolution**: Cucumber test binary runs from a different working directory than inline tests. Fixture paths may need adjustment (use `env!("CARGO_MANIFEST_DIR")`)

## Sources & References

- `cucumber` crate: docs.rs/cucumber/0.22.1, github.com/cucumber-rs/cucumber
- Existing test catalog: 86 unit tests + 1 doc-test across 13 modules
- Related code: `middens/src/parser/mod.rs`, `middens/src/techniques/mod.rs`
