---
title: "Fingerprint-based rerun and reuse for public results"
status: todo
priority: P2
tags: [ci, caching, reproducibility, public-results]
source: public-results-website-pipeline
---

## Why

Running full analysis and LLM interpretation for every scheduled workflow is wasteful if neither the corpus nor the process changed. We need explicit fingerprints so the pipeline reruns only when evidence or code/prompt/model inputs changed.

## What

Add fingerprint helpers, probably:

```bash
scripts/public_results_fingerprint.py
scripts/public_results_changed.py
```

Compute at least three fingerprint families.

### Corpus fingerprint

- registry entry;
- dataset repo/revision;
- storage format;
- materialized object hashes;
- normalizer name/version;
- generated JSONL count/hash summary.

### Analysis/process fingerprint

- repository git SHA;
- `middens` package version;
- Rust technique source hashes or technique manifest hash;
- Python technique source hashes;
- materializer source hash;
- relevant workflow/script hashes;
- analysis flags (`--all`, timeout policy, split mode, redaction flags).

### Interpretation fingerprint

- metrics input hash;
- prompt template hash;
- model/provider id;
- temperature/settings;
- interpretation script hash;
- comparative prompt/script hash for comparative outputs.

## Reuse source

First cut can read previous fingerprints from the generated `www` branch/site data. Later versions may use GitHub Actions cache or a release/artifact bucket.

## Done

- [ ] Each corpus result bundle records corpus/process/interpretation fingerprints.
- [ ] CI can skip unchanged per-corpus analysis when fingerprints match a previous published bundle.
- [ ] CI can skip unchanged per-corpus interpretation when metrics/prompt/model fingerprints match.
- [ ] CI can skip unchanged comparative interpretation when all comparative inputs match.
- [ ] Manual dispatch supports `force=true` to rerun everything.
- [ ] Website methodology page displays relevant fingerprints.
