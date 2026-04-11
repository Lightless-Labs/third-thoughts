---
title: "Two validation runs: source-built vs homebrew-installed"
status: todo
priority: P1
tags: [distribution, validation, workstream-3]
source: user-direction-2026-04-10
---

## What

Two full e2e runs that validate the distribution artifact works identically to a source build.

## Run 1: source-built

1. `cd middens && cargo install --path .`
2. `middens run <corpus>` (the e2e verb — depends on distribution-e2e-verb.md)
3. Stash the full export (notebook + manifest + parquet) somewhere for comparison.

## Run 2: homebrew-installed

1. Remove source-built middens (`cargo uninstall middens` or `rm $(which middens)`).
2. `brew install lightless-labs/tap/middens`
3. `middens run <corpus>` on the same corpus.
4. Stash this export separately.

## Comparison

Both exports should be structurally identical. UUIDs and timestamps will differ, but:
- Same techniques ran
- Same number of rows in each parquet file
- Same findings/figures in the manifest
- Notebook structure matches (same cells, same headings)

This catches anything that accidentally depends on the source tree, dev fixtures, or paths that only exist in a checkout.

## Sequencing

Depends on: distribution-e2e-verb.md, distribution-homebrew-tap.md
