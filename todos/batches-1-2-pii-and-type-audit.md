---
status: deferred
priority: P2
tags: [middens, audit, pii, storage, technique, correctness]
source: conversation 2026-04-09 (CLI triad milestone scoping)
blocked_by: [cli-triad-analyze-interpret-export]
---

# Audit Batches 1+2 techniques for PII leakage and type-homogeneous columns

## Why deferred

Originally listed as a **prereq** in `docs/design/output-contract.md` and `todos/output-contract.md`, but pulled out of the CLI triad milestone (2026-04-09) to keep that milestone shippable. The audit still has to happen before the storage layer can be trusted on a shared corpus — it just doesn't have to happen *before* the triad ships.

Run the audit either (a) immediately after the triad lands, before any real corpus export is shared externally, or (b) as part of the first distribution cut (workstream 3).

## What to audit

All techniques that were wired in Batches 1+2 (6 Rust + 8 Python from the earlier batches — the Batch 3 and Batch 4 NLSpecs already bake in the constraints, so they're out of scope here).

### PII audit (hard rule from `docs/design/output-contract.md` § "Table schema constraints")

For each technique, check every `DataTable` it emits for:

- [ ] Raw user message text
- [ ] Raw assistant message text
- [ ] Raw thinking-block content
- [ ] File paths (`cwd`, source paths, tool paths, log paths)
- [ ] Tool-call arguments (raw — tool *names* are permitted)
- [ ] Filenames (of corpus files, CLAUDE.md, MCP configs, anything under `corpus/`)
- [ ] Any `metadata.*` field that could be a user identifier

**Permitted in tables:** derived numerics, tool-name symbols (the name only, not the args), parser-assigned stable session IDs (hash or UUID from the parser — never a filesystem path), ISO timestamps, language codes, counts, ratios.

Expected finding count is low (techniques mostly compute numerics), but the audit has to be explicit before any exported notebook reaches a third party.

### Type-homogeneity audit

For each technique's `DataTable`:

- [ ] No column mixes ints and `"N/A"` strings. Use `null` for missing values.
- [ ] No column mixes ints and floats-as-strings.
- [ ] Booleans stored as `Bool`, not `"true"` / `"false"` strings.
- [ ] ISO timestamps stored as `Timestamp` (once `ColumnType` is added) or at least as consistent ISO-8601 strings.

Expected fix volume: <20 lines across the affected techniques.

## Deliverables

- [ ] A short audit report under `docs/reports/` listing every Batch 1+2 technique, its tables, and whether each passed PII + type checks.
- [ ] Fixes (if any) in the affected technique files + updated Cucumber scenarios covering the edge cases that the audit surfaces.
- [ ] Cross-reference from `docs/design/output-contract.md` pointing at the audit report so future readers can see it was done.

## Constraints

The audit reads technique output, not corpus data. Run it against a synthetic or small-public corpus — **do not paste real corpus tables into the audit report**, that would leak exactly the PII the audit is trying to prevent.

## Effort

Small-to-medium. Half a day of reading technique code + mechanical fixes + one report doc. Bigger if it surfaces a technique that needs genuine rework (unlikely — techniques were written with numerics-only in mind, even if nobody was checking).
