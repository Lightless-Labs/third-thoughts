---
title: "Public corpus results website pipeline"
status: todo
priority: P1
tags: [website, public-results, huggingface, ci, interpretation]
source: user-request-2026-05-28
---

## Why

We want a selected set of public datasets to have their latest `middens` results published to the website, with per-corpus analysis/interpretation and cross-corpus comparative analysis/interpretation rerun when either the corpus or the process changes.

Existing pieces cover the lower half of the stack: pinned HF registry, JSONL/Parquet materialization, full `middens analyze --all`, split smoke, notebook export, and GitHub Pages. Missing pieces are public-safe metric extraction, site generation, interpretation policy, comparative aggregation, and invalidation/reuse.

## What

Build an end-to-end public results pipeline:

1. select publishable corpora from `docs/corpora/public-hf-analysis-corpora.json`;
2. materialize each selected corpus;
3. run flat and split full analysis;
4. extract curated public-safe metrics;
5. optionally interpret each corpus from curated evidence only;
6. build comparative metrics across corpora;
7. optionally interpret the comparison;
8. generate static website pages;
9. publish to GitHub Pages;
10. rerun only when corpus/process/interpretation fingerprints change.

## Proposed phases

1. ~~Deterministic public result bundles (`todos/public-results-metrics-extraction.md`).~~ Done 2026-05-29.
2. ~~Static site generation and deploy (`todos/public-results-static-site-generation.md`).~~ Done 2026-05-29.
3. Per-corpus interpretation (`todos/public-results-per-corpus-interpretation.md`).
4. Comparative metrics + interpretation (`todos/public-results-comparative-interpretation.md`).
5. Fingerprint-based invalidation/reuse (`todos/public-results-fingerprint-invalidation.md`).

## Non-goals for the first cut

- Do not publish raw transcripts.
- Do not publish raw per-session tables by default.
- Do not run LLM interpretation on untrusted fork PRs.
- Do not pool duplicate-shaped corpora into one scientific headline.
- Do not make autonomous-loop behavior claims until a real non-empty autonomous cohort exists.

## Done

- [ ] Registry supports publish/interpret controls per corpus.
- [x] Selected corpora produce public-safe result bundles.
- [x] Website shows corpus cards and comparative deterministic metrics.
- [ ] Per-corpus interpretation is available for trusted runs.
- [ ] Comparative interpretation is available for trusted runs.
- [ ] Fingerprints skip unchanged reruns.
- [x] GitHub Pages deploy is automated.
- [ ] `docs/HANDOFF.md` records the current workflow, outputs, and caveats.
