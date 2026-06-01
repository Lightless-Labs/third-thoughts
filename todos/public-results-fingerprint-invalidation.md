---
title: "Fingerprint-based rerun and reuse for public results"
status: in_progress
priority: P2
tags: [ci, caching, reproducibility, public-results]
source: public-results-website-pipeline
---

## Why

Running full analysis and LLM interpretation for every scheduled workflow is wasteful if neither the corpus nor the process changed. We need explicit fingerprints so the pipeline reruns only when evidence or code/prompt/model inputs changed.

## What

Add fingerprint helpers, probably:

```bash
scripts/public_results_fingerprint.py
scripts/public_results_changed.py
```

Compute at least three fingerprint families.

### Corpus fingerprint

- registry entry;
- dataset repo/revision;
- storage format;
- materialized object hashes;
- normalizer name/version;
- generated JSONL count/hash summary.

### Analysis/process fingerprint

- repository git SHA;
- `middens` package version;
- Rust technique source hashes or technique manifest hash;
- Python technique source hashes;
- materializer source hash;
- relevant workflow/script hashes;
- analysis flags (`--all`, timeout policy, split mode, redaction flags).

### Interpretation fingerprint

- metrics input hash;
- prompt template hash;
- model/provider id;
- temperature/settings;
- interpretation script hash;
- comparative prompt/script hash for comparative outputs.

## Reuse source

First cut can read previous fingerprints from the generated `www` branch/site data. Later versions may use GitHub Actions cache or a release/artifact bucket.

## Progress

**Started:** 2026-05-31. Dedicated plan: `docs/plans/2026-05-31-public-results-fingerprint-invalidation-plan.md`.

Implemented the deterministic analysis-reuse layer: `scripts/public_results_fingerprint.py`, `scripts/public_results_changed.py`, extractor/site integration, `fingerprints.json` downloads, methodology display, prior-`www` reuse in `.github/workflows/hf-corpus-analysis.yml`, and workflow `force` input. Per-corpus interpretation fingerprint skip is wired through `scripts/interpret_public_corpus.py`; comparative interpretation fingerprint skip is wired through `scripts/interpret_public_comparison.py`.

## Done

- [x] Each corpus result bundle records corpus/process/interpretation fingerprints.
- [x] CI can skip unchanged per-corpus analysis when fingerprints match a previous published bundle.
- [x] CI can skip unchanged per-corpus interpretation when metrics/prompt/model fingerprints match.
- [x] CI can skip unchanged comparative interpretation when all comparative inputs match.
- [x] Manual dispatch supports `force=true` to rerun everything.
- [x] Website methodology page displays relevant fingerprints.
