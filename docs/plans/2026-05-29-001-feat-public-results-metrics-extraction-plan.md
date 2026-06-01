# Public results metrics extraction plan

**Created:** 2026-05-29

## Goal

Create the deterministic, public-safe metrics layer for the public corpus results website pipeline. This is Phase 1 of `todos/public-results-website-pipeline.md` and should run before any LLM interpretation or static-site polish.

## Scope

- Add `scripts/extract_public_corpus_metrics.py`.
- Input one public-HF corpus id, the registry entry, a flat `middens analyze --all` output/run manifest, a split `middens analyze --split` output/run manifest, and optionally the materialized corpus manifest.
- Output `site-data/corpora/<id>/` with:
  - `corpus.json` — safe registry/materialization provenance only;
  - `analysis-manifest.json` — sanitized run manifest without source paths or raw tables;
  - `split-manifest.json` — sanitized split manifest and stratum counts;
  - `metrics.json` — curated aggregate allowlist;
  - `status.json` — deterministic extraction status and warnings.
- Add fixture coverage for a JSONL corpus and a Parquet-derived corpus.
- Document the public-safe metric allowlist and the deliberately excluded classes of data.

## Privacy / safety rules

- Do not publish raw transcripts, prompts, assistant text, tool payloads, raw per-session rows, source paths, or session ids.
- Prefer numeric aggregate findings.
- String metrics must be allowlisted and either controlled vocabulary/codes or public provenance values.
- Missing/undefined metrics are represented as `null` plus status flags, not coerced to zero.
- Fail clearly on ambiguous inputs: unknown corpus id, missing manifests, unsupported registry schema, or missing required directories/files.

## Validation

- `python3 -m py_compile scripts/extract_public_corpus_metrics.py tests/test_extract_public_corpus_metrics.py`
- `python3 tests/test_extract_public_corpus_metrics.py`
- Smoke the script against existing local public-HF artifacts for at least:
  - `agent-sessions-list-mixed` (JSONL)
  - `archit11-claude-code-traces-parquet` (Parquet trace-row normalizer)

## Done criteria mapping

- Deterministic `metrics.json`: sort keys, no generation timestamp, stable ordering.
- Public-safe: allowlist-only metrics and sanitized manifests.
- Undefined distinct from zero: missing metrics object records `value: null` and `status`.
- Split counts/status: included under `metrics.session_counts.by_stratum` and `metrics.technique_status_by_stratum`.
- Fixture tests: JSONL + Parquet-derived.
- Methodology docs: new solution note for the allowlist.
