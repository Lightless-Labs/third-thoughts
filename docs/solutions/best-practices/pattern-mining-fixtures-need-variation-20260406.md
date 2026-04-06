---
title: Pattern-mining test fixtures need session-level variation
date: 2026-04-06
category: best-practices
module: middens
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - Writing tests for sequence-mining algorithms (PrefixSpan, SPADE, GSP)
  - Writing tests for sequence-alignment / motif extraction (Smith-Waterman, Needleman-Wunsch)
  - Writing tests for temporal pattern detection (T-patterns, HSMM)
  - Generating synthetic session fixtures from a deterministic template
tags: [testing, fixtures, pattern-mining, prefixspan, smith-waterman, python-bridge]
related_components: [bridge, techniques]
---

# Pattern-mining test fixtures need session-level variation

## Context

While building Cucumber tests for Batch 2 Python techniques in `middens` (PrefixSpan, Smith-Waterman motif extraction, T-pattern detection), the table assertions failed: techniques returned empty result tables even though the algorithm code was correct and the fixtures were valid, parseable sessions.

The root cause was the fixture generator. The original `make_tool_call` helper in `middens/tests/steps/python_batch1.rs` selected tools deterministically by turn index:

```rust
fn make_tool_call(turn: usize) -> ToolCall {
    let tools = ["Read", "Edit", "Bash", "Glob", "Grep"];
    let name = tools[turn % tools.len()]; // identical across all sessions
    // ...
}
```

Every generated session had the exact same tool sequence (`Read, Edit, Bash, Glob, Grep, Read, ...`). PrefixSpan found no discriminative patterns between the "low correction" and "high correction" groups because the sequences were identical. Smith-Waterman found zero conserved motifs because there was no inter-sequence variation to align against. The algorithms had nothing to discriminate, so they returned nothing.

## Guidance

When generating synthetic fixtures for pattern-mining or sequence-comparison algorithms, seed the generator with the **session index** so each session gets a distinct (but deterministic) trajectory:

```rust
fn make_tool_call_varied(turn: usize, session_idx: usize) -> ToolCall {
    let tools = ["Read", "Edit", "Bash", "Glob", "Grep", "Write", "Skill", "WebSearch"];
    let offset = session_idx * 3;                  // shift the tool window per session
    let name = tools[(turn + offset) % tools.len()];

    let dirs = ["src/", "src/parser/", "src/bridge/", "tests/", "python/", "docs/"];
    let dir = dirs[(turn + session_idx) % dirs.len()];
    // ...
}
```

Then thread `session_idx` through the session-builder (`create_session_indexed`) and update every fixture entry point (`given_sessions_with_turns`, `given_mixed_sessions`, etc.) to pass `i as usize` for each generated session.

Concrete checklist for fixtures feeding pattern-mining code:

1. **Variation between sessions** — different tool sequences and lengths.
2. **Variation within sessions** — mixed tool types, not the same call repeated.
3. **Enough samples** to satisfy the algorithm's minimum-support thresholds.
4. **Deterministic, not constant** — seed from the session index so runs are reproducible without being uniform.

## Why This Matters

Pattern-mining algorithms are specifically designed to find what is *common* against a backdrop of what *varies*. A fixture set with no variation is degenerate input: the algorithm has no signal to extract and returns empty. The failure mode is silent — the algorithm code is correct, the fixture data parses cleanly, the test just asserts against an empty table and fails.

This is a class of bug that masquerades as an algorithm bug or a contract bug, but is actually a fixture-design bug. Without recognising the pattern, you can spend hours instrumenting the algorithm and the bridge layer before realising the input is the problem.

After adding session-index variation, PrefixSpan found 12 frequent patterns and Smith-Waterman found 151 conserved motifs across the same 5-session fixture — and the table assertions passed.

## When to Apply

- Any test exercising sequence-mining (PrefixSpan, SPADE, GSP, BIDE)
- Any test exercising sequence alignment or motif extraction (Smith-Waterman, Needleman-Wunsch, MEME)
- Any test exercising temporal pattern detection (T-patterns, HSMM, change-point detection)
- More generally: any algorithm whose output depends on diversity between input samples

## Examples

**Symptom (uniform fixtures):**
- 5 sessions generated, all with sequence `[Read, Edit, Bash, Glob, Grep, Read, Edit, ...]`
- PrefixSpan output: empty patterns table
- Smith-Waterman output: 0 motifs
- Test assertion: `expected at least 1 row, got 0` — fails

**Fix (session-indexed fixtures):**
- 5 sessions generated, each shifted by `session_idx * 3` in tool space and `session_idx` in directory space
- PrefixSpan output: 12 frequent patterns with varying support
- Smith-Waterman output: 151 conserved motifs
- Test assertion: passes

## Related

- `middens/tests/steps/python_batch1.rs` — fixture helpers (`make_tool_call_varied`, `create_session_indexed`)
- `docs/solutions/integration-issues/python-rust-json-contract-gotchas-20260406.md` — adjacent learning from the same Python bridge work
- `docs/solutions/best-practices/cucumber-rs-setup-and-pitfalls-20260401.md` — broader Cucumber-rs testing practices for middens
