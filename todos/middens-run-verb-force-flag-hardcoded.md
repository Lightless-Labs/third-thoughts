---
title: "`middens run` hardcodes `force: true` on the export step"
status: todo
priority: P3
tags: [middens, cli, polish, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

The `run` verb chains `analyze → interpret → export` and hardcodes `force: true` on the export step, so any existing notebook at the output path is silently overwritten. The individual `export` subcommand, by contrast, respects a `--force` flag and defaults to failing on an existing file. The two verbs therefore have different safety semantics for the same underlying operation.

## Refs

- `middens/src/main.rs:499-506` — `run` verb's call to `export::run` with `force: true`
- `middens/src/commands/export.rs:72-76` — export's own `force` flag, default false

## Fix

Two reasonable paths:

1. **Add `--force` to `run`**: default to `false`, pass through to the export step. Users who want the overwrite behavior opt in explicitly, same as the standalone `export`.
2. **Document and keep**: if the `run` verb is meant to be an idempotent "re-run the whole pipeline" command, overwriting the export is the *correct* default. Add a help-text note saying so.

Option 1 is slightly safer and consistent; option 2 is a defensible product choice. Pick one before expanding the `run` verb further.

## Why

From the codex pre-release review: "verbs that do the same operation with different safety defaults are a low-grade footgun." Not severe, but cheap to fix and keeps the CLI surface coherent.

## Priority

P3 — nice-to-have polish. Not user-visible unless someone runs `run` twice against the same output dir and is surprised their notebook got overwritten.
