---
title: "Homebrew tap for middens"
status: todo
priority: P1
tags: [distribution, homebrew, workstream-3]
source: user-direction-2026-04-10
---

## What

Create a Homebrew tap (`Lightless-Labs/homebrew-tap` or similar) with a formula for `middens`.

## Steps

1. GitHub release workflow producing cross-platform binaries (darwin-arm64, darwin-x86_64, linux-x86_64, linux-arm64).
2. Create the tap repo with a formula that downloads the release binary + verifies SHA256.
3. `brew install lightless-labs/tap/middens` should Just Work.
4. Validate: uninstall any source-built middens, `brew install`, run full e2e (the `run` verb from distribution-e2e-verb.md), confirm output matches source-built run.

## Notes

- Homebrew is the primary distribution channel (target audience is researchers, not Rust devs).
- crates.io publish is secondary — can happen in parallel but isn't the critical path.
- The formula needs to handle the Python bridge gracefully — `uv` is a runtime dep for Python techniques, but the CLI degrades to Rust-only without it. Formula should `recommend` uv, not `depend` on it.
