---
title: "NLSpec: expand acceptance criteria for middens run"
status: todo
priority: P3
issue_id: null
tags: [cli, nlspec, run-verb, testing]
source: coderabbit-review-2026-04-14
---

## Problem

The Done section of `docs/nlspecs/run-verb-nlspec.md` only covers 6 acceptance criteria (happy paths + one error case). Several DoD behaviors have no corresponding test:

- `--no-interpretation` flag skips interpret step
- `--dry-run` writes prompt to disk, export handles absent interpretation output
- `--force` without `--timeout` fails with validation error
- Zero-session corpus produces "no sessions parsed" error
- Stderr contains the three progress lines (`→ analyzing...`, `→ interpreting...`, `→ exporting...`) and final summary
- Analyze/export failures produce non-zero exit codes with the right messages

## Action

Expand the Done section with items 7–12 covering the above. Each should specify the exact command invocation and expected observable outcome (exit code, stderr content, or file existence).

## Scope

Doc-only change to `docs/nlspecs/run-verb-nlspec.md`.
