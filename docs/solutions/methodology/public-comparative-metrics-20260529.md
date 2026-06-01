# Public comparative metrics layer

**Date:** 2026-05-29
**Context:** Deterministic half of public results pipeline Phase 4

## Problem

The generated public results site had per-corpus metric bundles and a simple side-by-side HTML table, but no durable comparative data product. That is too thin a substrate for future interpretation: an LLM summary should not be asked to infer replication, missing axes, or duplicate-corpus hazards from page markup.

## Decision

Add `scripts/build_public_comparative_metrics.py`. It consumes only Phase 1 public-safe corpus bundles under `site-data/corpora/<id>/` and writes deterministic JSON under `site-data/comparative/`:

- `corpus-index.json` — corpus provenance, session counts, stratum counts, warning codes, and duplicate-family hints;
- `technique-status-matrix.json` — technique completion/error/table-row status by corpus;
- `comparative-metrics.json` — selected allowlisted finding observations plus aggregate min/max/mean/status counts;
- `finding-replication-matrix.json` — classification inputs and caveats for selected findings.

The static site generator now renders the comparative JSON when it is present, and the HF corpus analysis workflow builds comparative metrics before rendering the site.

## Safety and interpretation rules

- The comparative script does not read raw transcripts, notebooks, Parquet files, or middens raw technique outputs.
- Undefined/redacted/missing metrics stay distinct from numeric zero.
- Duplicate-shaped `pi-mono`-family corpora are flagged rather than pooled as independent replications.
- Missing axes are explicit: language is unavailable until language detection lands; thinking visibility is not fully stratified in the comparative bundle; autonomous coverage is shown as stratum counts and corpus counts.
- The `classification_input` fields are inputs for later interpretation, not final claims. They intentionally use careful labels such as `direction_replicated_magnitude_variable`, `direction_consistent_zero`, `mixed`, and `not_tested`.

## Current selected comparative metrics

The first allowlist covers the website's main deterministic comparison table:

- thinking risk suppression;
- thinking/text divergence;
- mean, first-third, and last-third correction rates;
- MVT compliance;
- HSMM pre-correction lift;
- mean tool entropy;
- ENA top code.

This is enough for the public site and future comparative prompt to cite exact aggregate values without touching raw artifacts. It is not yet the comparative LLM interpretation layer.

## Validation

```bash
python3 -m py_compile scripts/build_public_comparative_metrics.py tests/test_build_public_comparative_metrics.py
python3 tests/test_build_public_comparative_metrics.py
```

Local smoke against `.tmp/site-data-all` produced all four comparative JSON files for six public-HF corpus bundles, then rebuilt `.tmp/site-out-test` and passed the site privacy grep.
