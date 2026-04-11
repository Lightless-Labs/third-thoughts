---
status: deferred
priority: P2
tags: [middens, interpret, parser, robustness]
source: NLSpec review 2026-04-09 (Codex finding)
blocked_by: [cli-triad-analyze-interpret-export]
---

# `interpret` response-parser strictness

## Why deferred

The CLI triad NLSpec defines how `interpret` parses a runner's response into per-technique conclusion files: split on `<!-- technique: <slug> -->` markers, content before the first marker becomes the overall `conclusions.md`. The v1 spec covers one failure mode (no markers at all → move to `interpretation-failures/`) but leaves three other edge cases undefined:

1. **Missing sections.** The analysis has N techniques, but the model only emits N-1 section markers. Is that fatal, or do the missing techniques silently get no conclusion file?
2. **Duplicate markers.** The model emits two `<!-- technique: hsmm -->` markers. Do we concatenate, pick the first, pick the last, or fail?
3. **Unknown slug markers.** The model emits `<!-- technique: pareto -->` but the analysis contains no `pareto` technique. Is that an extra file written, an error, or silently ignored?

v1 accepts whatever the model emits: at-most-one section per slug (later duplicates are concatenated with a separator), unknown slugs become their own `<slug>-conclusions.md` files, missing slugs silently get no file. This is permissive but hides problems.

## What

Tighten the parser and add scenarios for each edge case. The specific rules are a design decision, but the recommended default is:

- [ ] **Missing sections.** Fatal. A conclusion-per-technique is the whole point of `interpret`; if the model skipped one, either the prompt is wrong or the model misbehaved, and the user needs to know.
- [ ] **Duplicate markers.** Fatal. Don't try to reconcile — the model is confused and the output shouldn't be trusted.
- [ ] **Unknown slug markers.** Warn (write to stderr), write the unknown slug to the interpretation dir anyway, exit 0. The unknown slug doesn't invalidate the known ones, and the user might want to see what the model thought about a technique that wasn't run.
- [ ] **Empty section body.** Fatal. Same reason as missing.
- [ ] All four rules get Cucumber scenarios with mocked runner fixtures.
- [ ] The parser writes a diagnostic structure (as `error.txt` under `interpretation-failures/`) naming the specific rule violated, the marker(s) involved, and the response length — enough for a user to debug without re-running.

## Effort

Medium. ~150 lines of parser logic + 6 Cucumber scenarios + fixture responses. The parser design matters here — probably worth a short design note before implementation.
