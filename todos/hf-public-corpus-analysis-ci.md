---
title: "Establish HF-based public corpus analysis CI"
status: done
priority: P1
completed: 2026-05-25
tags: [ci, huggingface, corpus, middens, reproducibility]
source: user-direction-2026-05-25
---

## Why

Public HF datasets should not be silently pooled into one behavioural headline, but they also should not sit unanalyzed in a list of "candidates" forever. Establish a pinned HF-based corpus registry and CI path that runs the full middens analysis battery against each selected corpus, excluding the LLM interpretation layer.

## What

Implemented:

- `docs/corpora/public-hf-analysis-corpora.json` — pinned public HF corpus registry.
- `scripts/build_hf_corpus_registry_dataset.py` — builds an HF dataset folder containing `README.md`, `corpora.json`, and `corpora.jsonl`.
- `scripts/publish_hf_corpus_registry.py` — publishes the registry dataset when `HF_TOKEN` / login is available.
- `scripts/fetch_hf_corpus_registry.py` — fetches a published HF registry for CI/manual use.
- `scripts/hf_corpus_matrix.py` — emits GitHub Actions matrix JSON by tier/corpus id.
- `scripts/materialize_hf_analysis_corpus.py` — downloads a pinned HF dataset revision and materializes JSONL session logs for `middens analyze`.
- `.github/workflows/hf-corpus-analysis.yml` — PR/scheduled/manual CI workflow; supports optional HF registry repo/revision inputs or repo variables.
- `docs/solutions/methodology/hf-corpus-analysis-ci-20260525.md` — methodology and operational notes.

CI behavior:

1. Build `middens` from source.
2. Download/materialize selected pinned HF corpus.
3. Run `middens analyze <corpus> --all --timeout 1800 --force`.
4. Run `middens export --analysis-dir <run-dir> --no-interpretation`.
5. Validate manifest has 23 technique entries.
6. Upload analysis artifacts.

No `middens interpret` or LLM runner is invoked.

## Validation

Local smoke validation on `agent-sessions-list-mixed`:

- `python3 -m py_compile scripts/build_hf_corpus_registry_dataset.py scripts/fetch_hf_corpus_registry.py scripts/publish_hf_corpus_registry.py scripts/hf_corpus_matrix.py scripts/materialize_hf_analysis_corpus.py`
- `python3 scripts/build_hf_corpus_registry_dataset.py --output .tmp/hf-registry-dataset-test`
- `python3 scripts/publish_hf_corpus_registry.py --repo-id Lightless-Labs/third-thoughts-public-corpora` correctly fails early without an HF token.
- `python3 scripts/hf_corpus_matrix.py --tier smoke`
- `python3 scripts/materialize_hf_analysis_corpus.py --corpus agent-sessions-list-mixed --output .tmp/hf-ci-smoke --cache-dir .tmp/hf-cache-smoke --force`
- `XDG_DATA_HOME=$PWD/.tmp/xdg-ci-smoke ./middens/target/release/middens analyze .tmp/hf-ci-smoke --all --timeout 1800 --force --output .tmp/middens-ci-smoke`
- `middens export --analysis-dir <resolved-run-dir> --no-interpretation --output .tmp/reports-ci-smoke/agent-sessions-list-mixed.ipynb --force`

Result: 7 sessions parsed, 23/23 techniques completed, export succeeded, manifest had 23 technique entries.

## Follow-ups

- Actually publish the registry dataset once an HF token with org access is available:
  `HF_TOKEN=... python3 scripts/publish_hf_corpus_registry.py --repo-id Lightless-Labs/third-thoughts-public-corpora`.
- Add a streaming/schema-aware Parquet trace normalizer before enabling Parquet trace corpora for full analyze CI.
- Add `HF_TOKEN` repo secret if weekly full runs hit unauthenticated HF rate limits.
