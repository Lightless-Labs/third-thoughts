---
title: "Adversarial NLSpec contract must specify test framework conventions"
date: 2026-04-01
category: workflow-issues
module: foundry-adversarial
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "Writing NLSpecs for adversarial red/green development"
  - "Red team tests fail due to framework integration issues, not logic errors"
tags: [adversarial, nlspec, contract, red-green, testing, information-barrier]
---

# Adversarial NLSpec Contract Must Specify Test Framework Conventions

## Context

First real application of the adversarial red/green development process for the middens output engine. The red team (writing tests) and green team (writing implementation) operated behind an information barrier, communicating only through a Natural Language Specification (NLSpec) contract. Post-delivery, 64/178 tests (36%) failed — and every single failure was caused by contract gaps in the NLSpec, not by implementation bugs. The NLSpec specified *what* to test but not *how* the test framework worked, leaving the red team to guess at framework conventions it had never seen.

## Guidance

### 1. The NLSpec contract section must specify test framework conventions

The contract is the only communication channel between red and green teams. Any assumption not stated in the contract will be guessed differently by each side. For a Cucumber-rs test suite, the contract must specify:

- **State management**: "All scenario state lives in a `World` struct. No thread-local storage, no global statics. The World is constructed fresh per scenario."
- **Step matching modes**: "Use `expr = "..."` for simple patterns with `{int}/{float}/{string}/{word}` placeholders. Use `regex = r#"..."#` for patterns containing literal brackets `[]`, braces `{}`, or other special characters that Cucumber Expressions cannot represent."
- **Complex value escaping**: "Gherkin step text is plain text. To pass JSON-like values, embed them literally: `Given a finding with value [1,2,3]` — the step definition uses regex mode to parse."
- **Step type strictness**: "`#[given]` only matches Given, `#[when]` only matches When, `#[then]` only matches Then."

### 2. Run a "contract smoke test" before full delivery

Before the red team writes 178 scenarios, verify the integration surface with 3-5 trivial scenarios against a stub implementation. This catches framework mismatches (wrong step macro syntax, import issues, World struct shape) at a cost of minutes rather than hours. If the smoke scenarios pass end-to-end, the contract's framework conventions section is adequate.

### 3. Classify post-delivery failures correctly

When tests fail after the green team delivers, classify each failure before acting:

| Failure type | Meaning | Action |
|--------------|---------|--------|
| **Contract gap** | The NLSpec did not specify a convention the red team needed to know | Refine the NLSpec, then re-deliver to both teams |
| **Red bug** | The test itself has a logic error (wrong assertion, wrong setup) | Feedback to red team only. NEVER show implementation code |
| **Green bug** | The implementation does not meet the NLSpec | Send PASS/FAIL results to green team. NEVER show test code |

The classification matters because different failure types require different information flows. Mixing them breaks the information barrier.

### 4. The orchestrator must NEVER write code during the adversarial phase

The orchestrator coordinates, classifies failures, and refines the NLSpec. The moment the orchestrator writes or modifies test code or implementation code, it has seen both sides and provenance is broken. There is no longer any guarantee that the tests are independent of the implementation. In the middens output engine case, the orchestrator reconciled test failures directly, voiding the correctness guarantee — there was no way to verify the tests had not been inadvertently gamed to match the implementation.

### 5. Use different AI tools for red/green teams

Natural context isolation is stronger than prompt-based isolation. Use different tools for each team:

- **Red team** (tests): Codex CLI, Gemini CLI, or OpenCode — tools that operate in a subprocess with no shared memory
- **Green team** (implementation): A different tool from the red team
- **Orchestrator**: The primary agent (e.g., Claude), which sees the NLSpec and failure classifications but never sees raw code from either side

This prevents accidental context leakage where the LLM "remembers" implementation details when writing tests or vice versa.

### 6. Delegation: match tool to task

Not all adversarial work units are equal. Match the delegation tool to the work:

- **CLI tools** (codex, gemini, opencode): Best for self-contained units where the full context fits in the NLSpec. The subprocess boundary enforces isolation.
- **Subagents**: Best for work requiring broader crate context (e.g., the green team needs to understand existing module structure). Use `mode: bypassPermissions` to avoid interactive prompts.
- **Inline (orchestrator)**: Only for surgical fixes that are mechanical and require no judgment (e.g., fixing an import path). The orchestrator seeing the code for a mechanical fix is lower risk than a full round-trip through delegation.

## Why This Matters

The adversarial red/green process is designed to produce tests whose correctness is independent of the implementation. When the contract has gaps, the orchestrator is forced to reconcile failures by examining both sides, which breaks the information barrier and voids the independence guarantee. In the middens case, the orchestrator reconciled directly, meaning there is no way to verify whether the 178 tests actually catch real bugs or were shaped to match the implementation. The 36% failure rate was entirely preventable — every failure traced back to a convention that was obvious to anyone who had seen the codebase but invisible from the NLSpec alone.

## When to Apply

- Writing any NLSpec that will be consumed by an agent behind an information barrier
- First time using adversarial red/green on a new test framework
- Debugging high failure rates post-delivery where failures cluster around framework integration rather than logic
- Reviewing whether an adversarial process maintained its information barrier integrity

## Examples

**NLSpec contract section — before (caused 36% failure rate):**

> Tests should be written as Cucumber scenarios in `.feature` files with step definitions in Rust.

**NLSpec contract section — after (prevents framework failures):**

> **Test Framework Conventions:**
>
> - Test framework: cucumber-rs 0.22 with `futures = "0.3"`.
> - State: All mutable state lives in `MiddensWorld` (the World struct). Fields available: `sessions: Vec<Session>`, `technique_result: Option<TechniqueResult>`, `cli_output: String`, `error: Option<String>`, `output_path: Option<PathBuf>`. No thread-local or global state.
> - Step matching: Use `expr = "..."` for simple patterns. Use `regex = r#"..."#` when step text contains `[]`, `{}`, or regex-special characters.
> - Step types: `#[given]` matches only Given steps, `#[when]` matches only When steps, `#[then]` matches only Then steps. Cucumber-rs does not treat them as interchangeable.
> - Fixture paths: Use `env!("CARGO_MANIFEST_DIR")` to resolve paths relative to crate root.
> - Assertions: Use standard `assert!`, `assert_eq!`, `assert!(x.contains(...))`. Panic = test failure.

**Contract smoke test (3 scenarios):**

```gherkin
Feature: Contract smoke test

  Scenario: World struct initializes
    Given the test harness is initialized
    Then the harness should be operational

  Scenario: Simple step matching works
    Given a session with 5 messages
    Then the session count should be 1

  Scenario: Regex step matching works
    Given a finding "test" with array value [1,2,3] described as "smoke"
    Then the finding count should be 1
```

If all three pass, the contract's framework section is adequate for full-scale test authoring.

## Related

- Foundry orchestrator provenance issue: `docs/solutions/workflow-issues/orchestrator-reconciliation-breaks-provenance-20260401.md`
- Cucumber-rs setup pitfalls: `docs/solutions/best-practices/cucumber-rs-setup-and-pitfalls-20260401.md`
- NLSpec used for the output engine: `docs/nlspecs/2026-04-01-output-engine-nlspec.md`
