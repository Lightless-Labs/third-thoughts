---
title: "Extract public-safe corpus result metrics"
status: todo
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

- [ ] Script produces deterministic `metrics.json` for every analysis-enabled public HF corpus.
- [ ] No raw transcript text, tool payloads, raw paths, or raw per-session tables are emitted.
- [ ] Missing/undefined metrics are represented distinctly from numeric zero.
- [ ] Split counts and technique status are included.
- [ ] Fixture tests cover at least one JSONL corpus and one Parquet-derived corpus.
- [ ] Methodology docs describe the public-safe metric allowlist.
