---
title: "Add schema-aware normalizers for public HF Parquet trace datasets"
status: done
priority: P2
tags: [huggingface, parquet, parser, normalizer, public-corpus]
source: public-hf-23-technique-analysis-2026-05-26
---

## Why

Several public Claude Code trace datasets are visible on Hugging Face but are not raw JSONL session logs. The first `archit11/claude-code-traces` adapter handled one simple Parquet request/response schema for HSMM-only exploratory work, but the full `middens analyze` CI path currently expects raw JSONL corpus directories.

Unsupported Parquet/schema variants mean public Claude Code coverage is thinner than public Pi coverage.

## What

Add schema-aware, streaming-safe normalization for public Parquet trace datasets so they can become first-class corpora in `docs/corpora/public-hf-analysis-corpora.json` and CI.

Candidate datasets from the 2026-05-23/25 survey:

- `archit11/claude-code-traces`
- `archit11/claude_code_traces_hs`
- `archit11/claude_code_traces_dirty`
- `nlile/misc-merged-claude-code-traces-v1`

## How

1. Inspect schemas without committing raw rows/snippets.
2. Define a normalized `Session[]` or JSONL materialization contract that preserves:
   - message role/order;
   - tool calls/results where present;
   - model/timestamp metadata;
   - reasoning/thinking observability labels where inferable.
3. Implement normalizers outside the core parser first, likely under `scripts/`, then decide whether to promote into `middens` proper.
4. Update `scripts/materialize_hf_analysis_corpus.py` to materialize supported Parquet corpora for CI.
5. Enable one Parquet trace corpus in `docs/corpora/public-hf-analysis-corpora.json` and run full `middens analyze --all` + `export --no-interpretation`.

## Done

- [x] At least one Parquet trace dataset is normalized into a `middens analyze`-compatible corpus (`archit11-claude-code-traces-parquet`).
- [x] Large Parquet datasets are handled without loading multi-GB data into memory at once (`pyarrow.parquet.ParquetFile.iter_batches`).
- [x] Unsupported schemas fail clearly with expected columns/examples.
- [x] CI includes at least one non-Pi Parquet-derived corpus (full tier).
- [x] Sanitized methodology note documents schema decisions and caveats: `docs/solutions/methodology/public-hf-parquet-trace-normalizer-20260528.md`.
