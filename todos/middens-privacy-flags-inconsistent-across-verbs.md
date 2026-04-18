---
title: "Privacy flags `--include-project-names` / `--include-source-paths` are partial no-ops on `interpret` and `export`"
status: todo
priority: P2
tags: [middens, cli, privacy, correctness, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17-round2
---

## What

The B2 PII-scrubbing work wired `--include-source-paths` and `--include-project-names` onto all four user-facing verbs (`analyze`, `run`, `interpret`, `export`) so the flags look consistent. They are not. On `interpret` and `export` the `--include-project-names` flag is effectively a no-op because the ipynb renderer never consults `RedactionConfig.include_project_names` when emitting per-project tables — only `analyze`-time techniques do the hashing, and by the time `export` runs those values are frozen in the parquet. Same for any downstream consumer of the analysis artifacts.

A user who forgets the flag at `analyze` time and later re-exports with `--include-project-names` gets a scrubbed notebook, not a revealed one. There is no way to recover the raw project names after analysis without re-running the pipeline. That is arguably the *safer* default, but it is not what the flag help text promises.

## Refs

- `middens/src/main.rs:110-169` — clap derive advertising the flags on all four verbs
- `middens/src/commands/interpret.rs:397-402` — interpret config passes redaction through, but the data is already frozen
- `middens/src/commands/export.rs:72-76` — export config ditto
- `middens/src/techniques/correction_rate.rs` — where the hashing actually happens (analyze-time)
- `middens/src/bridge/technique.rs` — `forward_env()` only matters when Python techniques run (analyze-time)
- `middens/src/view/ipynb.rs` — renderer does not read `RedactionConfig.include_project_names`

## Options

1. **Document the asymmetry**: keep the flag on `interpret`/`export` but add a help-text note that it only affects freshly-analyzed data, and that existing parquet data is frozen at analyze-time settings. Cheapest and honest.
2. **Remove the flag from `interpret`/`export`**: breaking, but unambiguous. The flag only appears where it does something.
3. **Store raw + scrubbed both at analyze-time**: doubles artifact size and defeats the point of scrubbing. Don't do this.
4. **Wire the renderer to re-scrub at export-time**: possible for paths (stored in manifest JSON) but not for project names (already hashed in parquet). Partial solution.

Recommend option 1 for the beta and re-evaluate after real users hit the edge case.

## Fix

1. Update `analyze`/`run` help text for both flags: "Controls redaction in analysis artifacts. Must be set at analyze time; ignored by interpret/export on already-analyzed data."
2. Update `interpret`/`export` help text: "Only affects source paths in the notebook metadata. Project-name redaction is frozen at analyze time and cannot be changed post-hoc."
3. Add a paragraph to the middens README on the semantics.

## Why

From the codex round-2 review: "flags that exist on all four verbs but only do something on one are a footgun." Consistent with the repo-level CLAUDE.md rule "Fail early, fail fast, fail clearly" — silent partial behavior is exactly what that rule is meant to prevent.

## Priority

P2 — correctness-adjacent. The scrubbing still works correctly at analyze time (which is the load-bearing case); the gap is only visible to users who try to un-scrub post-hoc and are surprised nothing happens.
