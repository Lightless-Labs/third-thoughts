---
title: "Scrub test coverage asserts key presence, not redaction correctness"
status: todo
priority: P2
tags: [middens, testing, privacy, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17-round2
---

## What

The cucumber scenarios added in the B2 PII-scrubbing work verify that scrubbed keys (`project_name`, `project_path`, `notebook.middens.source_paths`) exist in the output — they do not verify that the values at those keys are actually scrubbed. A regression that leaks raw project names or absolute paths into any of those keys would still pass the scenarios as long as the keys exist.

Concretely: a test like "the notebook has a `project` field in its metadata" passes whether the value is `project_d298391b` (correctly scrubbed) or `/Users/thomas/Projects/lightless-labs/third-thoughts` (broken). The green count from the B2 commits is therefore weaker evidence than it looks.

## Refs

- `middens/tests/features/cli-triad/` — scenarios that check metadata key presence
- `middens/tests/steps/pipeline.rs` — step implementations for scrub assertions
- `middens/src/view/ipynb.rs` — renderer that actually produces the scrubbed values
- `middens/src/techniques/correction_rate.rs` — `emitted_project_name()` hashing logic
- `middens/python/techniques/cross_project_graph.py`, `corpus_timeline.py` — Python-side hashing

## Fix

Tighten the assertions to shape-match the scrubbed values:

1. **Project names**: assert the value matches `^project_[0-9a-f]{8}$` (or is `unknown`), not just that the key exists. Add a negative assertion that no value contains `/` or matches the raw corpus project name used in the test fixture.
2. **Source paths**: assert the value is a basename (no `/`) when `--include-source-paths` is not set. Add a negative assertion for leading `/Users/` or `/home/` substrings.
3. **Interpretation path in notebook metadata**: assert the value matches `^interpretation/[a-z0-9-]+$` when scrubbing is on. (This was the round-2 blocker — worth a dedicated regression test.)
4. Add a scenario for the inverse: with `--include-project-names` / `--include-source-paths`, values should be raw and contain the fixture's known path substring.

The existing "key present" assertions can stay as a first-cut sanity check, but the shape assertions need to be added alongside them.

## Why

From the codex round-2 review: "The green count gives false confidence. The regression that leaks a raw path is still test-passing under the current assertions." This matches a past compound pattern documented in `docs/solutions/` — assertions that check for presence without checking for shape are a well-known antipattern.

## Priority

P2 — the scrubbing code is correct today (verified manually against real corpus in the B2 smoke tests), but the tests do not *enforce* that it stays correct. Strong post-beta priority; not a blocker for the tag.
