---
title: "Per-corpus public results interpretation"
status: in_progress
priority: P1
tags: [interpretation, public-results, llm, prompts]
source: public-results-website-pipeline
---

## Why

The public website should include readable per-corpus summaries, but they must be grounded in curated aggregate metrics, not raw transcripts or arbitrary technique tables. Interpretation also needs pinned prompts/models and rerun controls because LLM outputs are costly and less deterministic than the analysis battery.

## What

Add a per-corpus interpretation path that consumes only public-safe evidence:

```text
site-data/corpora/<id>/metrics.json
site-data/corpora/<id>/analysis-manifest.json
site-data/corpora/<id>/split-manifest.json
```

Potential script:

```bash
scripts/interpret_public_corpus.py \
  --corpus-dir site-data/corpora/<id> \
  --prompt docs/prompts/public-corpus-interpretation-v1.md \
  --model <model> \
  --output site-data/corpora/<id>/interpretation.md
```

The prompt must require:

- cite exact metric values;
- state session counts and stratum coverage;
- distinguish zero from undefined/not enough data;
- avoid headlines on tiny N;
- mention thinking-visibility/language/autonomous gaps;
- no pooled claims;
- no transcript quotes;
- no private-path/project speculation.

## Security / CI policy

- Run only on trusted scheduled/manual pushes with provider credentials.
- Do not run on fork PRs.
- Store model id, prompt hash, input metrics hash, and output hash.
- Prefer skipping if the interpretation fingerprint is unchanged.

## Progress

**Started:** 2026-05-31. Dedicated plan: `docs/plans/2026-05-31-public-results-per-corpus-interpretation-plan.md`.

Implemented the first optional per-corpus interpretation path: `docs/prompts/public-corpus-interpretation-v1.md`, `scripts/interpret_public_corpus.py`, metadata/fingerprint output, unchanged-fingerprint skip, unsafe marker checks, site download support for `interpretation.json`, and trusted CI wiring via repo variables `PUBLIC_RESULTS_INTERPRET_MODEL` + `PUBLIC_RESULTS_INTERPRET_COMMAND`.

2026-06-01 Codex prompt review approved the per-corpus prompt with no P1/P2 findings after checking curated-evidence, metric-citation, split-count, privacy, missing-axis, duplicate-corpus, and tone requirements. Review note: `docs/reviews/2026-06-01-public-results-interpretation-prompts-codex-review.md`.

2026-06-01 local provider-backed smoke passed using Codex CLI as the stdin/stdout runner against a copied `agent-sessions-list-mixed` site-data bundle under `.tmp/provider-smoke/`: `scripts/interpret_public_corpus.py` wrote `interpretation.{md,json}`, the generated site built, and privacy grep passed. Still needs a trusted GitHub workflow/provider smoke before calling the whole path boring in the good way.

## Done

- [x] Prompt template exists and is reviewed.
- [x] Script produces `interpretation.md` and `interpretation.json` metadata.
- [x] Interpreter consumes only curated public-safe inputs.
- [x] CI can run interpretation on trusted events.
- [x] Website renders per-corpus interpretation when available.
- [x] Unchanged fingerprints skip LLM calls.
