---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: high
tags: [cli-design, middens, analyze, interpret, export, contract]
applies_when:
  - designing the Middens CLI command surface
  - adding new analytical techniques to the pipeline
  - deciding where LLM-based interpretation belongs in the workflow
---

# Middens CLI contract: the analyze / interpret / export triad

## Context

The Middens CLI initially had a single `analyze` command that ran
techniques, rendered views, and wrote outputs in one pass. Two
pressures pushed us off that design:

1. The analytical techniques are expensive and deterministic; the
   LLM-driven interpretation layer is expensive and
   non-deterministic. Fusing them means every rerun of the
   interpretation re-runs the analysis, and every analysis rerun
   discards any interpretation that was layered on top.
2. Output rendering (Markdown, JSON, ASCII, eventually Jupyter) is
   a view concern that has nothing to do with either phase. Baking
   renderers into `analyze` made it impossible to re-export a past
   result in a new format without re-running the whole pipeline.

## Guidance

Middens exposes three top-level commands, each with a single
responsibility:

    middens analyze     # run techniques, produce canonical TechniqueResult store
    middens interpret   # run LLM interpretation over a stored analysis
    middens export      # render a stored analysis or interpretation into a view

Each command reads from and writes to the canonical on-disk store.
None of them shortcut into another's responsibility. A user can:

- re-interpret last week's analysis with a better prompt, without
  re-running techniques;
- re-export an interpretation into a Jupyter notebook without
  touching the LLM;
- rerun analysis on new data while keeping historical
  interpretations intact.

**Jupyter export is the first-class view format**, not Markdown or
JSON. The rationale: Jupyter preserves both the structured data and
the rendered narrative in a single file, it is the native artifact
for the research audience, and it is the format whose structure
forces `analyze` and `interpret` to stay cleanly separated (code
cells vs markdown cells). Markdown and JSON remain available as
thinner views, but they are downstream of the notebook format.

## Why This Matters

Three commands instead of one is a deliberate un-collapse. The
single-command version optimizes for the happy path ("run everything
once, get a report") at the cost of every other path. The triad
optimizes for the iteration loops that actually dominate research
work:

- Techniques get added and tuned → re-run `analyze` often, keep
  interpretations stable.
- Interpretation prompts evolve → re-run `interpret` often, keep
  analyses stable.
- Export formats change → re-run `export` cheaply, keep everything
  else stable.

Fusing any two of these phases forces cascading reruns and loses
work. The cost of three commands is a few extra lines of CLI
plumbing; the benefit is that each phase can be iterated without
disturbing the others, and each phase has an obvious caching
boundary.

## When to Apply

- Adding a new command to Middens: ask which of the three phases it
  belongs to. If it doesn't fit any, the triad may need to grow —
  but the default is "no."
- Adding a new technique: it lives inside `analyze`, writes to the
  canonical store, and never touches rendering or LLM calls.
- Adding a new output format: it lives inside `export`, reads from
  the canonical store, and never re-runs anything.

## Examples

**Wrong (fused):**

    middens analyze --with-interpretation --format markdown

One command, three responsibilities, no caching boundaries, every
rerun re-does everything.

**Right (triad):**

    middens analyze corpus/ --out ~/.local/.../analysis/2026-04-07-batch5/
    middens interpret ~/.local/.../analysis/2026-04-07-batch5/ \
        --out ~/.local/.../interpretation/2026-04-07-batch5-claude/
    middens export ~/.local/.../interpretation/2026-04-07-batch5-claude/ \
        --format jupyter --out report.ipynb

Each command is independently re-runnable. Each has a single
caching boundary. The canonical store is the contract between
phases.

Related:
- `docs/solutions/design/middens-storage-view-split-20260407.md`
- `docs/solutions/design/middens-default-path-scheme-20260407.md`
- `docs/solutions/design/middens-llm-provider-fallback-chain-20260407.md`
