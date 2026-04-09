---
status: deferred
priority: P3
tags: [middens, export, ux, safety]
source: NLSpec review 2026-04-09 (Gemini finding)
blocked_by: [cli-triad-analyze-interpret-export]
---

# `middens export -o` overwrite UX

## Why deferred

The CLI triad NLSpec specifies that `middens export -o report.ipynb` silently overwrites any pre-existing file at that path. This is the simplest behaviour and unblocks the milestone, but it's also the least safe — a user who re-runs `export` with a stale analysis selected can overwrite a notebook they haven't committed or shared yet, with no recovery path.

## What

Add opt-in safety rails for the common "I didn't mean to overwrite that" failure mode:

- [ ] **Default behaviour: refuse to overwrite.** If `-o <file>` points at an existing file, exit non-zero with `refusing to overwrite existing file <path>; pass --force to overwrite or -o <different-path>`.
- [ ] **`--force` flag:** explicitly opts into overwriting.
- [ ] **Backup mode (optional):** consider `--backup` that renames the existing file to `<file>.bak` before writing. Probably not worth the complexity if `--force` covers the intentional case.
- [ ] **Cucumber scenarios:**
  - Default: pre-existing output file → non-zero exit, file untouched.
  - `--force`: pre-existing output file → overwritten, exit 0.
  - No pre-existing file: either default or `--force` → file written, exit 0.
- [ ] **Migration note:** this is a *behaviour change* from the v1 silent-overwrite default. Document in the release notes that scripts relying on silent overwrite need to add `--force`.

## Open question

Whether the same refusal applies to the default `report.ipynb` in cwd when `-o` is omitted. Yes, for consistency. Users who want silent overwrite set `--force`; users who want a fresh filename pass `-o`.

## Effort

Small. ~20 lines of command-side logic + 3 Cucumber scenarios.
