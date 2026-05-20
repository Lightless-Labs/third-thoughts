---
title: "Two validation runs: source-built vs homebrew-installed"
status: done
priority: P1
tags: [distribution, validation, workstream-3]
source: user-direction-2026-04-10
---

## What

Two full e2e runs that validate the distribution artifact works identically to a source build.

**Public corpus option:** Pi coding-agent sessions uploaded via `pi-share-hf` are public JSONL corpora on Hugging Face (for example `badlogicgames/pi-mono`). Middens on `main` and the Homebrew `v0.0.1-beta.1` artifact now parse this envelope as `SourceTool::PiCodingAgent`, so Step D can use a small downloaded slice of a public Pi dataset instead of exposing the private Lightless Labs corpus.

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

Parser dependency satisfied for the public-HF path: Pi coding-agent JSONL support landed with `middens/src/parser/pi.rs`, and the Homebrew tap was updated through `v0.0.1-beta.3` by 2026-05-20.

## Completed: 2026-05-20

Validation completed against a deterministic 10-session public slice from `badlogicgames/pi-mono` (`pi-share-hf` JSONL). Both runs used `middens run <corpus> --all -o <report.ipynb>` with isolated XDG data/config/cache directories:

- Source-built binary: `cargo install --path middens --root /tmp/.../source-root --locked` → `middens 0.0.1-beta.3`
- Homebrew binary: `brew install/reinstall lightless-labs/tap/middens` → `middens 0.0.1-beta.3`

Comparison result:

- 10 sessions discovered and parsed in both runs
- 23 techniques ran in both runs
- 21 parquet files emitted in both runs
- Manifest matched after excluding expected `run_id` / `created_at` differences and allowing tiny floating-point tolerance
- Parquet schemas, row counts, and rows matched with numeric tolerance
- Notebook structure matched after normalizing expected run-id/timestamp heading differences: 68 cells, 88 headings

Local validation artifact root: `/tmp/third-thoughts-step-d-beta3-20260520172206` (not committed; safe to delete).

During validation, two nondeterminism bugs were found and fixed before the final passing run:

1. `information_foraging.py` selected a representative patch via `list(set)[0]`; fixed by sorting the candidate patches.
2. `tpattern_detection.py` used an unseeded permutation test; fixed with a deterministic NumPy RNG seed.

Those fixes shipped in `v0.0.1-beta.3`, and the Homebrew tap was updated to that release.
