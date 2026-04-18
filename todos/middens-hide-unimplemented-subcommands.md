---
title: "Hide or implement `report` and `fingerprint` subcommands"
status: todo
priority: P2
tags: [middens, cli, polish, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

`middens --help` still advertises `report` and `fingerprint` as subcommands, but both only print `[not yet implemented]`. For a public beta, that is a bad first impression. Either implement them, or mark them `hide = true` in the clap derive until they work.

## Refs

- `middens/src/main.rs:67-75` — clap derive for the two subcommands
- `middens/src/main.rs:104-107` — subcommand enum variants
- `middens/src/main.rs:323-329` — `Commands::Report` handler (prints placeholder)
- `middens/src/main.rs:381-384` — `Commands::Fingerprint` handler (prints placeholder)

## Options

1. **Hide them**: add `#[command(hide = true)]` to the variants. Users who type them explicitly still see the `[not yet implemented]` output; `--help` stays clean.
2. **Implement them**: `fingerprint` is probably cheap (just print `AnalyzerFingerprint` for a run). `report` is larger — what should it do that `export` doesn't?

Hiding is the 5-minute fix; implementing is a feature-scoping exercise.

## Why

From the pre-release review: shipping placeholder subcommands in `--help` for `v0.0.1-beta.0` is "release-day embarrassment for first-time users."

## Priority

P2 — cosmetic but visible. Not a blocker for the beta tag, but worth knocking out before 0.0.1-beta.1.
