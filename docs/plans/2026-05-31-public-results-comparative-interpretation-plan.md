# Public results comparative interpretation plan

**Created:** 2026-05-31
**Enhanced:** 2026-05-31 (initial implementation)

## Goal

Add an optional comparative interpretation layer over deterministic public-safe comparative JSON. It should explain cross-corpus patterns without pooling duplicate-shaped corpora into fake replication confetti.

## Scope

- Prompt template for comparative interpretation.
- Python interpreter wrapper for `site-data/comparative/` bundles.
- Metadata/fingerprint output and unchanged-input skip.
- Static-site rendering/download support.
- Optional trusted CI hook controlled by repo variables.

## Non-goals

- Per-corpus interpretation; already handled separately.
- Provider-specific SDK integration.
- Any raw transcript/session-table access.

## Implementation steps

1. Add fixture tests for response-file execution, skip-on-unchanged fingerprint, site rendering, and unsafe marker rejection.
2. Add `docs/prompts/public-comparative-interpretation-v1.md`.
3. Implement `scripts/interpret_public_comparison.py` over `corpus-index.json`, `comparative-metrics.json`, `technique-status-matrix.json`, and `finding-replication-matrix.json`.
4. Update `scripts/build_public_results_site.py` to render/copy `comparative/interpretation.{md,json}`.
5. Add optional trusted workflow step controlled by `PUBLIC_RESULTS_COMPARATIVE_INTERPRET_MODEL` and `PUBLIC_RESULTS_COMPARATIVE_INTERPRET_COMMAND`.
6. Update docs/todos/handoff and validate.

## Done criteria

- [x] Prompt template exists.
- [x] Script produces `interpretation.md` and `interpretation.json` from comparative JSON only.
- [x] Unchanged comparative interpretation fingerprints skip model calls.
- [x] Website renders comparative interpretation when present.
- [x] CI can invoke comparative interpretation on trusted non-PR runs when configured.
- [x] Tests and actionlint pass.
- [ ] Prompt has an external/human review note.
- [ ] A trusted provider-backed workflow run has been smoke-tested.
