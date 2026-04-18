---
title: "Validate `export --analysis-dir A --interpretation-dir B` belong together"
status: todo
priority: P2
tags: [middens, cli, correctness, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

`middens export --analysis-dir A --interpretation-dir B` does not validate that the interpretation at B was produced from the analysis at A. It only checks that `B/manifest.json` exists and parses. That means it is easy to produce a notebook with technique data from one run and narrative conclusions from an entirely different run, with no warning.

## Refs

- `middens/src/commands/export.rs:28-50` — export config + argument handling
- `middens/src/storage/discovery.rs:71-84` — interpretation manifest load (no cross-ref check)
- `middens/tests/features/cli-triad/export.feature:36-40` — feature currently codifies the mismatch as acceptable

## Fix

On export, after loading both manifests, assert
`analysis.run_id == interpretation.analysis_run_id`. Bail with a clear message on mismatch:

```
middens: export: interpretation at <B> was produced for run <X>, not <Y>.
Use the matching --interpretation-dir or regenerate the interpretation.
```

Update the cucumber scenario to assert the bail, not the silent success.

## Why

Silent coercion violates the "fail early, fail fast, fail clearly" principle in the repo-level CLAUDE.md. The current behavior lets a user build a report where the tables and the narrative disagree, with no way to notice.

## Priority

P2 — correctness bug, but narrow blast radius (only manifests if the user explicitly wires two incompatible dirs). Not a beta-tag blocker.
