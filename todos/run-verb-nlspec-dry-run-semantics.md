---
title: "NLSpec: clarify --dry-run semantics for middens run"
status: todo
priority: P3
issue_id: null
tags: [cli, nlspec, run-verb]
source: coderabbit-review-2026-04-14
---

## Problem

The NLSpec for `middens run` (`docs/nlspecs/run-verb-nlspec.md`) has two inconsistencies around `--dry-run`:

1. **How vs DoD contradiction** (line 128): The How section says "export still runs against whatever interpretation output exists, or without it if none exists" when `--dry-run` is set. The DoD implies the export only uses fresh analysis output. These are contradictory — if `--dry-run` writes a prompt but doesn't call a runner, and export picks up existing/stale interpretation output from a prior run, the user gets a misleading notebook. The canonical behavior needs to be chosen and documented.

2. **`--dry-run` without `--model`** (line 97): The `do_interpret` logic is `model.is_some() && !no_interpretation`, but there's no validation for `--dry-run` with no `--model`. Should it error? Be a no-op?

## Resolution options

**Option A** (recommended): When `--dry-run` is set, force `ExportConfig.no_interpretation = true`. Export always runs analysis-only — no stale interpretation output is consumed. Update How + DoD to reflect this.

**Option B**: Allow opportunistic use of existing interpretation output. Weaker guarantee, harder to reason about.

For `--dry-run` without `--model`: treat as a no-op (dry_run is silently ignored when there's no model to call). Document this explicitly in the NLSpec.

## Scope

Doc-only change to `docs/nlspecs/run-verb-nlspec.md`. The implementation in `main.rs` may already behave correctly per Option A (verify before touching code).
