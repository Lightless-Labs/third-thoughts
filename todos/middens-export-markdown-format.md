---
status: deferred
priority: P3
tags: [middens, export, view, renderer]
source: NLSpec review 2026-04-09 (CodeRabbit + Gemini findings on scenario 9)
blocked_by: [cli-triad-analyze-interpret-export]
---

# `middens export --format markdown`

## Why deferred

The CLI triad NLSpec (`docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md`) declares Jupyter as the only `--format` value supported by `export` in v1. However, `analyze` already emits a `default-view.md` through the same `MarkdownRenderer::render(&AnalysisRun)` path the view layer uses — the rendering capability exists inside the binary, it's just not exposed as a user-facing `export` format.

Scenario 10 of the NLSpec covers this at the renderer level (byte-equality between analyze-emitted `default-view.md` and a fresh `MarkdownRenderer::render` call in-test), but users who want to re-render the markdown view from an existing analysis run can't invoke it via `export` today. They either re-run `analyze` or copy the `default-view.md` out of the run directory by hand.

## What

- [ ] Expose `markdown` as a valid `--format` value on `middens export`.
- [ ] Wire `MarkdownRenderer::render(&AnalysisRun)` to the export command's format dispatch.
- [ ] Default output file extension: `.md`. Default filename: `report.md`.
- [ ] Interpretation injection: if an interpretation is loaded, prepend the overall `conclusions.md` as a top-level `## Conclusions` section at the head of the report body, per the original conclusions-v1 design.
- [ ] Cucumber scenarios:
  - `export --format markdown` produces a file that is byte-equal to the analysis run's `default-view.md` when no interpretation is loaded.
  - `export --format markdown` with an interpretation loaded produces a file whose first section after the title is `## Conclusions` with the overall `conclusions.md` text.

## What is *not* in scope

- No HTML-from-markdown conversion (that's a separate renderer).
- No custom markdown flavors (GitHub-flavored is the default; no flags to switch to CommonMark-only or similar).

## Effort

Small. The renderer already exists. ~50 lines of command-side wiring plus 2–3 Cucumber scenarios.
