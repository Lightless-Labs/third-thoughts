# Public results per-corpus interpretation plan

**Created:** 2026-05-31
**Enhanced:** 2026-05-31 (initial implementation)

## Goal

Add the first public-safe LLM interpretation layer for individual corpus pages. The interpreter must consume only curated `site-data` bundles, produce markdown plus metadata, and skip unchanged inputs when the interpretation fingerprint matches. No transcript spelunking; no tool-payload soup; no accidentally quoting some poor person's prompt.

## Scope

- Prompt template for per-corpus interpretation.
- Python interpreter wrapper that accepts curated corpus bundles and either runs a configured stdin-based command or writes a dry-run prompt.
- Metadata/fingerprint output for rerun skipping.
- Site/download support for interpretation metadata.
- Optional trusted CI hook controlled by repo variables, never PR secrets.

## Non-goals

- Comparative interpretation in this step.
- Hard-coding a provider-specific SDK or secret format.
- Running interpretation on fork PRs.

## Implementation steps

1. Add fixture tests for prompt construction, response-file execution, skip-on-unchanged fingerprint, and unsafe content rejection.
2. Add `docs/prompts/public-corpus-interpretation-v1.md` with strict evidence/caveat requirements.
3. Implement `scripts/interpret_public_corpus.py`:
   - read only `metrics.json`, `analysis-manifest.json`, and `split-manifest.json` from `site-data/corpora/<id>/`;
   - compute prompt/input/model/script fingerprint;
   - write `interpretation.md` + `interpretation.json`;
   - update `fingerprints.json` interpretation section when present;
   - support `--dry-run`, `--response-file` for tests, and `--runner-command` for trusted CI;
   - fail clearly on unsafe raw markers.
4. Update `scripts/build_public_results_site.py` to download `interpretation.json`.
5. Wire optional trusted workflow step via repo variables.
6. Update docs/todos/handoff and run targeted tests.

## Done criteria

- [x] Prompt template exists.
- [x] Script produces `interpretation.md` and `interpretation.json` from curated inputs only.
- [x] Unchanged interpretation fingerprints skip model calls.
- [x] CI can invoke interpretation on trusted non-PR runs when configured.
- [x] Website downloads include interpretation metadata.
- [x] Tests and actionlint pass.
- [ ] Prompt has an external/human review note.
- [ ] A trusted provider-backed workflow run has been smoke-tested.
