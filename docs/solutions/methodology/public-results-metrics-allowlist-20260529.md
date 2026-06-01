# Public results metrics allowlist

**Date:** 2026-05-29
**Context:** Phase 1 of the public results website pipeline

## Problem

`middens` technique outputs are research artifacts, not website payloads. Several tables contain per-session rows, session ids, source-path-like strings, project hints, tool names, and other values that are fine locally but should not be blindly published to GitHub Pages. The public site needs deterministic aggregate evidence packs that later static-site and interpretation steps can consume without spelunking arbitrary output files.

## Decision

Add `scripts/extract_public_corpus_metrics.py`. It emits a curated `site-data/corpora/<id>/` bundle:

- `corpus.json` — public registry provenance plus materialization counts/fingerprint;
- `analysis-manifest.json` — sanitized flat run manifest;
- `split-manifest.json` — sanitized split run manifest and stratum technique status;
- `metrics.json` — allowlisted aggregate metrics only;
- `status.json` — deterministic extraction status and warnings.

The script accepts a public corpus id, the registry, the flat and split middens output directories, the flat and split run directories, and optionally the materialized HF corpus directory/manifest.

## Allowlist rules

Allowed values are intentionally boring:

1. Public corpus provenance: dataset repo, pinned revision, storage format, source category, and normalizer name.
2. Aggregate counts: materialized JSONL files, parsed sessions, estimated parse errors, technique completion/error counts, and split counts for `interactive`, `subagent`, and `autonomous`.
3. Numeric or boolean top-level findings from a fixed per-technique label allowlist.
4. A small set of controlled string findings with strict regex validation, e.g. ISO dates, `3/7`-style ratios, ENA code names, behavior-code motifs, and `increasing|decreasing|flat|unknown` survival trends.
5. `null` for missing/undefined metrics. Missing is not coerced to zero.

## Deliberately excluded

The extractor does **not** publish:

- raw transcript text;
- user prompts or assistant responses;
- tool inputs, tool outputs, or tool payloads;
- raw per-session tables;
- session ids;
- local or dataset-side source paths;
- project names;
- dynamic tool-name findings such as Markov self-loop labels or burstiest-tool names;
- cross-project hub/authority names;
- peak-frustration or most-volatile session ids;
- convention names that may be derived from paths or project-specific terms.

The sanitized manifests retain run ids, analyzer fingerprints, corpus fingerprints without `source_paths`, technique status, error counts, and table row counts. They omit raw error strings and table contents.

## Warnings

The bundle records warnings for interpretation hazards:

- tiny cohorts (`n < 30`);
- empty or tiny autonomous strata;
- language axis unavailable until language detection lands;
- possible duplicate-shaped `pi-mono` family corpora;
- parse-count mismatch between materialized files and parsed sessions;
- split stratum manifest counts that disagree with top-level split counts, which helps catch stale artifacts from the historical split-cache bug.

## Validation

Fixture tests cover both a JSONL corpus and a Parquet-derived corpus:

```bash
python3 -m py_compile scripts/extract_public_corpus_metrics.py tests/test_extract_public_corpus_metrics.py
python3 tests/test_extract_public_corpus_metrics.py
```

Local smoke runs were also performed against existing public-HF artifacts for `agent-sessions-list-mixed` and `archit11-claude-code-traces-parquet`.
