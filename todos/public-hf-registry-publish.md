---
title: "Publish public HF corpus registry dataset"
status: todo
priority: P2
tags: [huggingface, ci, corpus, registry, credentials]
source: hf-corpus-analysis-ci-2026-05-26
---

## Why

The public corpus registry is currently repo-local and CI can already use it. The tooling also supports a first-class Hugging Face dataset-of-corpora registry, but actual publication requires an HF token / org write access. Publishing is useful for decoupling corpus definitions from repo commits and letting manual/scheduled CI fetch a registry revision from HF.

No analysis path currently depends on this. It is optional polish, not a blocker.

## What

Publish the generated registry dataset to Hugging Face, then configure CI to consume it when desired.

Expected dataset contents:

- `README.md` — dataset card;
- `corpora.json` — canonical registry;
- `corpora.jsonl` — one registry row per corpus for HF preview.

## How

1. Authenticate locally or in a trusted environment:

   ```bash
   huggingface-cli login
   # or
   export HF_TOKEN=...
   ```

2. Build and publish:

   ```bash
   python3 scripts/build_hf_corpus_registry_dataset.py \
     --output .tmp/hf-corpus-registry-dataset

   HF_TOKEN=... python3 scripts/publish_hf_corpus_registry.py \
     --repo-id Lightless-Labs/third-thoughts-public-corpora
   ```

3. Optionally set GitHub repository variables for scheduled runs:

   - `HF_CORPUS_REGISTRY_REPO=Lightless-Labs/third-thoughts-public-corpora`
   - `HF_CORPUS_REGISTRY_REVISION=main` or a pinned commit SHA

4. Manually dispatch `.github/workflows/hf-corpus-analysis.yml` with `registry_repo` / `registry_revision` to validate remote-registry mode.

## Done

- [ ] Registry dataset exists on Hugging Face.
- [ ] `scripts/fetch_hf_corpus_registry.py --repo-id ...` can fetch `corpora.json` anonymously or with token as appropriate.
- [ ] Manual CI dispatch using `registry_repo` succeeds.
- [ ] If using scheduled remote registry, GitHub repo variables are set.
- [ ] `docs/HANDOFF.md` is updated with the published repo/revision.
