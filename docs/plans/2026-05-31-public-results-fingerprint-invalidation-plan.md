# Public results fingerprint invalidation plan

**Created:** 2026-05-31
**Enhanced:** 2026-05-31 (analysis-reuse implementation)
**Completed:** 2026-06-01 (first-cut analysis + interpretation fingerprint reuse wired)

## Goal

Add deterministic fingerprints to the public results pipeline so repeated trusted runs can reuse unchanged public-safe corpus bundles instead of rerunning the full `middens` battery every time. Token-burning for future interpretation should be opt-in, not a surprise garnish.

## Scope

- Per-corpus fingerprint bundle covering corpus, analysis/process, and interpretation inputs.
- Public-safe output only: no raw paths, session ids, transcript text, tool payloads, or per-session rows.
- A comparison helper that can tell CI whether a previous published bundle is reusable.
- GitHub Actions wiring with an explicit `force=true` escape hatch.
- Website/download/methodology surfacing of fingerprints.

## Non-goals

- No provider-specific LLM SDK implementation in this step; interpretation scripts remain command-driven.
- No GitHub Actions cache or artifact-bucket layer yet; first reuse source is the generated `www` branch/site output.
- No transcript-level publication of materialization details.

## Implementation steps

1. Add tests for fingerprint generation/comparison and site/extractor integration.
2. Implement `scripts/public_results_fingerprint.py`:
   - hash registry entry and materialization object summaries;
   - hash relevant repo/process sources and analysis flags;
   - hash interpretation settings/metrics prompt inputs when present;
   - emit `fingerprints.json` with stable schema and no raw object paths.
3. Implement `scripts/public_results_changed.py` for reusable/non-reusable decisions.
4. Update `extract_public_corpus_metrics.py` to emit `fingerprints.json` and record fingerprint digests in `status.json`.
5. Update site generation to copy/download/display fingerprint metadata.
6. Wire `.github/workflows/hf-corpus-analysis.yml` to fetch prior `www` bundles, compare fingerprints after materialization, skip unchanged analysis unless forced, and upload reused bundles.
7. Validate with targeted Python tests and a workflow syntax sanity read-through.

## Done criteria

- [x] Tests cover deterministic fingerprints, raw-path redaction, changed/unchanged comparison, extractor output, and site downloads/methodology text.
- [x] Each corpus bundle contains `fingerprints.json`.
- [x] Workflow dispatch has a `force` input.
- [x] Non-PR runs can reuse prior `www` site-data when corpus/process fingerprints match.
- [x] Docs/todos/handoff reflect the new status.
- [x] Interpretation-specific skip wiring is added once per-corpus/comparative LLM interpretation exists.
