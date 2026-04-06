# Conclusions v1 — Manual / Analyst-Authored

**Status:** Deferred until storage/view reshape ships
**Blocked by:** `todos/output-contract.md`
**Related:** `docs/design/output-contract.md` § "Where findings, conclusions, and tables live"
**Created:** 2026-04-06

## Why

`middens analyze` produces per-technique findings, summaries, and tables, but **never cross-technique narrative** — techniques run independently and middens doesn't synthesize at analyze time. When a human reads a full report they want a top-level "here's what all of this means together." That content has to come from somewhere, and the cleanest place is a post-hoc annotation over frozen storage.

v1 is the dumb-simple manual path: an analyst writes a markdown file, the report picks it up. No new command, no LLM, no magic.

## What

- [ ] **Add `conclusions_ref: Option<String>` to `manifest.json`** — relative path, typically `"conclusions.md"`. Absent = no conclusions.
- [ ] **Auto-detect `conclusions.md`** in the run directory at report-render time. If present and `conclusions_ref` is unset, treat it as if `conclusions_ref: "conclusions.md"` were set. Write-back to the manifest is optional (probably skip — keeps the manifest immutable post-analyze).
- [ ] **Renderer integration:**
  - `.ipynb` renderer: insert conclusions as a markdown cell at position 1 (right after the title/metadata cell).
  - `.md` renderer: insert conclusions as a `## Conclusions` section at the top of the report body, before per-technique sections.
  - `.html` renderer: same, styled as a callout at the top.
  - `.json` renderer: include as a `conclusions: <string>` top-level field.
- [ ] **No schema validation** on the conclusions content — it's freeform markdown. Renderers pass it through.
- [ ] **Document the workflow** in `docs/design/output-contract.md` and in `middens report --help`: "Drop a `conclusions.md` in the run directory to have it rendered at the top of reports."

## What is explicitly *not* in v1

- No `middens conclude` command — just edit the file.
- No LLM authoring (that's v2, `todos/conclusions-v2-synthesize.md`).
- No templating — conclusions are plain markdown.
- No per-technique conclusions — it's a single top-level document. Per-technique narrative already lives in the technique's summary.

## Properties

- **Post-hoc**: written after analyze, never during.
- **Optional**: missing file → report renders without a conclusions section.
- **Replaceable**: rewrite the file, views pick up the new text on next render.
- **Version-controllable independently**: git-track `conclusions.md` alongside the manifest without touching Parquet.
- **Forward-compatible with v2**: v2 (`middens synthesize`) writes the same file format. Renderers don't care which produced it.

## Effort estimate

Small — roughly 30 lines across manifest writer/reader and the three renderers. Can land in the same PR as the initial `.ipynb` renderer or immediately after.
