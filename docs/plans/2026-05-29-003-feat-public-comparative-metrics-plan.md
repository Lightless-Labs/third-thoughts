# Public comparative metrics plan

**Created:** 2026-05-29

## Goal

Implement the deterministic half of the comparative public results layer before adding any LLM interpretation. The comparative layer should consume only Phase 1 public-safe corpus bundles and produce stable JSON inputs for the generated website and future interpretation prompts.

## Scope

- Add `scripts/build_public_comparative_metrics.py`.
- Input: `site-data/corpora/<id>/metrics.json` plus adjacent `corpus.json` / `status.json` when present.
- Output `site-data/comparative/` with:
  - `corpus-index.json`
  - `comparative-metrics.json`
  - `technique-status-matrix.json`
  - `finding-replication-matrix.json`
- Update `scripts/build_public_results_site.py` to render comparative output when present, while retaining a fallback table from per-corpus metrics.
- Update HF CI to build comparative metrics after collecting per-corpus site-data and before rendering the site.
- Add fixture tests.

## Safety rules

- Do not read raw analysis outputs, notebooks, Parquet files, or transcripts.
- Do not pool duplicate-shaped corpora as independent evidence; flag duplicate-family candidates explicitly.
- Keep `N=0`, undefined, redacted, and not-run distinct from numeric zero.
- Deterministic JSON only: sorted corpus ids, sorted technique ids, sorted keys.

## Validation

- `python3 -m py_compile scripts/build_public_comparative_metrics.py tests/test_build_public_comparative_metrics.py`
- `python3 tests/test_build_public_comparative_metrics.py`
- Existing site tests continue to pass.
- Smoke against `.tmp/site-data-all` if present.

## Done criteria mapping

- Deterministic comparative metrics script exists.
- Duplicate-shaped corpora are warned, not pooled.
- Missing autonomous/language/thinking-visibility axes are explicit.
- Website renders deterministic comparative metrics from `site-data/comparative`.
