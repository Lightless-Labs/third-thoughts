---
title: "Per-corpus public results interpretation"
status: todo
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

## Done

- [ ] Prompt template exists and is reviewed.
- [ ] Script produces `interpretation.md` and `interpretation.json` metadata.
- [ ] Interpreter consumes only curated public-safe inputs.
- [ ] CI can run interpretation on trusted events.
- [ ] Website renders per-corpus interpretation when available.
- [ ] Unchanged fingerprints skip LLM calls.
