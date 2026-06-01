---
title: "Extract public-safe corpus result metrics"
status: done
priority: P1
tags: [website, public-results, metrics, privacy]
source: public-results-website-pipeline
---

## Why

The website should publish curated aggregate evidence, not raw technique outputs. Some technique JSON tables can contain session ids, path-ish strings, project hints, tool names, or other material that should not be copied blindly to GitHub Pages.

A deterministic `metrics.json` layer also gives the comparative analysis and LLM interpretation a clean evidence pack instead of asking them to spelunk arbitrary output files.

## What

Add a script such as:

```bash
scripts/extract_public_corpus_metrics.py \
  --corpus-id <id> \
  --registry docs/corpora/public-hf-analysis-corpora.json \
  --analysis-output .tmp/middens-results/<id> \
  --split-output .tmp/middens-split-results/<id> \
  --analysis-dir <xdg-run-dir> \
  --split-analysis-dir <xdg-split-run-dir> \
  --output site-data/corpora/<id>
```

Output:

```text
site-data/corpora/<id>/
  corpus.json
  analysis-manifest.json
  split-manifest.json
  metrics.json
  status.json
```

`metrics.json` should include only public-safe aggregate fields:

- corpus provenance and pinned revision;
- materialization normalizer/version;
- session counts;
- parse errors;
- technique completion/error counts;
- split counts: interactive/subagent/autonomous;
- selected aggregate findings from each technique;
- missing/undefined flags;
- warnings for tiny N, duplicate-shaped corpora, unsupported language/autonomous axes.

## Done

- [x] Script produces deterministic `metrics.json` for every analysis-enabled public HF corpus.
- [x] No raw transcript text, tool payloads, raw paths, or raw per-session tables are emitted.
- [x] Missing/undefined metrics are represented distinctly from numeric zero.
- [x] Split counts and technique status are included.
- [x] Fixture tests cover at least one JSONL corpus and one Parquet-derived corpus.
- [x] Methodology docs describe the public-safe metric allowlist.

## Completion notes

Completed 2026-05-29. Implementation: `scripts/extract_public_corpus_metrics.py`; tests: `tests/test_extract_public_corpus_metrics.py`; methodology: `docs/solutions/methodology/public-results-metrics-allowlist-20260529.md`; plan: `docs/plans/2026-05-29-001-feat-public-results-metrics-extraction-plan.md`.

Local smoke generated `.tmp/site-data-all/corpora/<id>/` bundles for all six currently analysis-enabled public HF corpora (five JSONL plus `archit11-claude-code-traces-parquet`) and passed a privacy grep for `source_paths`, raw-session fixture strings, transcript/tool-result markers, and local absolute paths. These smoke bundles are local artifacts, not committed website data.
