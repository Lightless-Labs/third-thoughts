---
title: "HF-based public corpus analysis CI"
module: third-thoughts
date: 2026-05-25
problem_type: methodology
component: ci-validation
severity: medium
status: implemented
tags:
  - huggingface
  - ci
  - corpus
  - middens
  - reproducibility
---

# HF-based public corpus analysis CI

## What changed

We now have a pinned public Hugging Face corpus registry and a CI workflow that can run the full `middens analyze --all` battery against each selected corpus, then export a notebook **without** invoking the LLM interpretation layer. The workflow also runs a lightweight `middens analyze --split --no-python` smoke on the same materialized HF corpus so session-type stratification regressions are tested against public data rather than stale private Claude Code symlinks.

The key distinction is deliberate: candidate public datasets should not be pooled into one shiny headline by default, but they absolutely can be analyzed independently. The previous framing skipped that middle path. Whoops, etc.

## Files

- Registry: `docs/corpora/public-hf-analysis-corpora.json`
- HF dataset builder: `scripts/build_hf_corpus_registry_dataset.py`
- HF registry publisher: `scripts/publish_hf_corpus_registry.py`
- HF registry fetcher: `scripts/fetch_hf_corpus_registry.py`
- Matrix helper: `scripts/hf_corpus_matrix.py`
- Materializer: `scripts/materialize_hf_analysis_corpus.py`
- Workflow: `.github/workflows/hf-corpus-analysis.yml`

## Registry shape

Each corpus entry records:

- stable local `id`;
- Hugging Face dataset repo and pinned revision;
- storage format;
- whether it is currently `analysis_enabled`;
- CI tiers (`smoke`, `representative`, `full`);
- minimum expected JSONL file/session counts;
- notes about provenance and caveats.

Initial analysis-enabled corpora:

| Corpus id | Dataset revision | CI tier |
|---|---|---|
| `agent-sessions-list-mixed` | `cfahlgren1/agent-sessions-list@10d6d295cb79a11194cfd93f0e9752b76889fbba` | smoke, representative, full |
| `badlogicgames-pi-mono` | `badlogicgames/pi-mono@dac2a1d3ba12dda597b973a791a77618ccb5f413` | representative, full |
| `thomasmustier-pi-for-excel` | `thomasmustier/pi-for-excel-sessions@1b7218d2acf621e52bb5208435b1f80154342e3f` | full |
| `aaaaliou-pi-mono` | `aaaaliou/pi-mono@61eee21d662f8736ace59507fc30555e1bff5c6e` | full |
| `kimi-claude-code-traces-jsonl` | `armand0e/kimi-k2.6-claude-code-traces@1f02263eb3c1d41f9d7b264baf56a09063a67963` | full |
| `archit11-claude-code-traces-parquet` | `archit11/claude-code-traces@416248040ba2c706c475bba238782c3e334fd4d8` | full |

Known but not yet analysis-enabled:

| Corpus id | Reason |
|---|---|
| `salt-nlp-swe-chat` | Strong candidate with 5.8k-ish transcript JSONL files, but the dataset is gated. Unauthenticated transcript download returns 401, so CI needs accepted HF-token access before enabling it. A one-off token smoke on 2026-05-26 downloaded three transcripts and `middens analyze --split --no-python` parsed all three. README says user prompts and assistant text responses were redacted with Microsoft Presidio + TruffleHog; still audit thinking/tool/code fields before calling outputs privacy-safe. |

## CI behavior

Workflow: `.github/workflows/hf-corpus-analysis.yml`.

Triggers:

- PRs touching workflow, registry, `middens/**`, or the helper scripts run the `smoke` tier.
- Weekly scheduled runs execute the `full` tier.
- Manual dispatch supports `tier={smoke,representative,full}`, `corpus=<id>|all`, and optional `registry_repo` / `registry_revision` inputs. If `registry_repo` is empty, CI uses the repo-local registry. If set, CI fetches `corpora.json` from that HF dataset repo and uses the resolved registry artifact for all matrix jobs. Scheduled runs can also use repository variables `HF_CORPUS_REGISTRY_REPO` and `HF_CORPUS_REGISTRY_REVISION`.

For each selected corpus, CI:

1. builds `middens` from source;
2. materializes the pinned HF corpus into `.tmp/hf-corpora/<id>` as analyze-compatible JSONL (raw JSONL copy for `storage_format=jsonl`; generated JSONL for supported `storage_format=parquet_trace_rows`);
3. runs:

   ```bash
   middens analyze .tmp/hf-corpora/<id> --all --timeout 1800 --force
   ```

4. resolves the XDG analysis run directory;
5. runs:

   ```bash
   middens export --analysis-dir <run-dir> --no-interpretation --output <id>.ipynb --force
   ```

6. validates that the manifest contains all 23 technique entries;
7. runs a split-stratification smoke:

   ```bash
   middens analyze .tmp/hf-corpora/<id> --split --no-python
   ```

   and validates that the top-level split manifest references `interactive`, `subagent`, and `autonomous` stratum manifests;
8. uploads the flat technique output, split smoke output, notebook, and manifest as CI artifacts.

No `middens interpret` or `middens run --model ...` step is used.

## Publishing the registry to Hugging Face

Build a dataset folder locally:

```bash
python3 scripts/build_hf_corpus_registry_dataset.py \
  --output .tmp/hf-corpus-registry-dataset
```

Publish it once authenticated:

```bash
HF_TOKEN=... python3 scripts/publish_hf_corpus_registry.py \
  --repo-id Lightless-Labs/third-thoughts-public-corpora
```

This uploads:

- `README.md` — HF dataset card;
- `corpora.json` — canonical registry JSON;
- `corpora.jsonl` — one corpus entry per row for the HF dataset preview.

Current local environment note: no Hugging Face token was present, so the publish command correctly failed early with a token-specific error. The tooling is ready; actual publication needs an authenticated token / org access.

## Local validation

Validated locally on the smoke corpus:

```bash
python3 -m py_compile scripts/hf_corpus_matrix.py scripts/materialize_hf_analysis_corpus.py
python3 scripts/hf_corpus_matrix.py --tier smoke
python3 scripts/materialize_hf_analysis_corpus.py \
  --corpus agent-sessions-list-mixed \
  --output .tmp/hf-ci-smoke \
  --cache-dir .tmp/hf-cache-smoke \
  --force
XDG_DATA_HOME=$PWD/.tmp/xdg-ci-smoke \
  ./middens/target/release/middens analyze .tmp/hf-ci-smoke \
  --all --timeout 1800 --force --output .tmp/middens-ci-smoke
XDG_DATA_HOME=$PWD/.tmp/xdg-ci-smoke \
  ./middens/target/release/middens export \
  --analysis-dir <resolved-run-dir> \
  --no-interpretation \
  --output .tmp/reports-ci-smoke/agent-sessions-list-mixed.ipynb \
  --force
```

Smoke result: 7 sessions parsed, 23/23 techniques completed, export succeeded, manifest had 23 technique entries. The split smoke on the same HF corpus parsed 7 sessions and produced three strata: 5 interactive, 2 subagent, 0 autonomous.

## Caveats / next steps

- The registry can now be published as a first-class Hugging Face dataset, but actual publication requires an HF token. Once published, set `HF_CORPUS_REGISTRY_REPO` / `HF_CORPUS_REGISTRY_REVISION` repository variables or use the manual workflow inputs.
- Several public candidate datasets are duplicate-shaped (`*-pi-mono`). Keep them separate for CI coverage, but do not count them as independent scientific replication without deduplication.
- One Parquet trace-row schema is now supported (`archit11-claude-code-traces-parquet`); additional Parquet variants still need schema-specific adapters before joining the full-analysis CI path.
- `SALT-NLP/SWE-chat` should be promoted once a trusted CI HF token has accepted gated access and we settle the secrets/trigger strategy. Keep it out of unauthenticated PR CI until then. Its documented Presidio/TruffleHog redaction is a major plus, but not a substitute for checking every field middens consumes.
- Weekly `full` runs may hit HF unauthenticated rate limits; add `HF_TOKEN` as a repo secret if that becomes noisy.
