---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: high
tags: [cli-design, middens, storage, rendering, separation-of-concerns]
applies_when:
  - adding output formats to Middens
  - designing the on-disk representation of analysis results
  - deciding where rendering logic lives
---

# Middens storage/view split: canonical TechniqueResult, renderers as a separate command

## Context

Early Middens conflated the in-memory analytical result with its
Markdown rendering. Every technique returned a pre-rendered string.
This worked for a single output format, but any attempt to add JSON,
ASCII, or Jupyter required either parsing Markdown back out (fragile)
or re-running the technique (expensive). It also made LLM
interpretation hard: the interpreter wanted structured data, but the
pipeline only produced text.

The fix is a clean split: the canonical representation on disk is a
typed `TechniqueResult` store, and all rendering is a pure function
from that store to a view format.

## Guidance

- **One canonical form.** `TechniqueResult` is the only
  representation anything writes to disk. It is structured,
  versioned, and format-agnostic. Techniques produce it; nothing
  else does.
- **Views are pure derivations.** Every renderer (Markdown, JSON,
  ASCII, Jupyter) is a pure function `TechniqueResult → bytes`. A
  renderer may not call back into the pipeline, invoke an LLM, or
  mutate state.
- **`export` is the only command that renders.** `analyze` writes
  the canonical store; `interpret` writes a separate interpretation
  store that also references the canonical store; `export` is the
  only place renderers live.
- **Adding a new format is a pure addition.** No technique, no
  pipeline code, and no existing renderer changes when a new
  format is introduced.

## Why This Matters

The split makes the expensive things (techniques, LLM calls)
independent from the cheap things (rendering). A bad Markdown
template does not cost a pipeline rerun to fix. A new output
format does not require touching 23 technique files. And the LLM
interpreter gets to consume the same canonical store that the
human-facing renderers consume, which means the two can never
drift — the narrative and the structured data are derived from a
single source of truth.

It also makes the canonical store the natural snapshotting
boundary for reproducibility. A frozen `TechniqueResult` bundle is
enough to regenerate any view, now or in a year, without the
original pipeline being runnable.

## When to Apply

- Any new technique: produces a `TechniqueResult`, nothing else.
- Any new output format: a new renderer in `export`, nothing else.
- Any new consumer (LLM interpreter, dashboard, diffing tool):
  reads the canonical store, never the rendered views.

## Examples

**Wrong:**

    impl Technique for Foo {
        fn run(&self, sessions) -> String { /* returns Markdown */ }
    }

**Right:**

    impl Technique for Foo {
        fn run(&self, sessions) -> TechniqueResult { /* structured */ }
    }

    // separately, in export/
    fn render_markdown(r: &TechniqueResult) -> String { ... }
    fn render_json(r: &TechniqueResult) -> String { ... }
    fn render_jupyter(r: &TechniqueResult) -> Notebook { ... }

Related:
- `docs/solutions/design/middens-analyze-interpret-export-triad-20260407.md`
- `docs/solutions/design/middens-default-path-scheme-20260407.md`
