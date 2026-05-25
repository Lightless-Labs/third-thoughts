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

We now have a pinned public Hugging Face corpus registry and a CI workflow that can run the full `middens analyze --all` battery against each selected corpus, then export a notebook **without** invoking the LLM interpretation layer.

The key distinction is deliberate: candidate public datasets should not be pooled into one shiny headline by default, but they absolutely can be analyzed independently. The previous framing skipped that middle path. Whoops, etc.

## Files

- Registry: `docs/corpora/public-hf-analysis-corpora.json`
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

Known but not yet analysis-enabled:

| Corpus id | Reason |
|---|---|
| `archit11-claude-code-traces-parquet` | Parquet request/response rows need a promoted normalizer before raw `middens analyze` can consume them as a corpus directory. |

## CI behavior

Workflow: `.github/workflows/hf-corpus-analysis.yml`.

Triggers:

- PRs touching workflow, registry, `middens/**`, or the helper scripts run the `smoke` tier.
- Weekly scheduled runs execute the `full` tier.
- Manual dispatch supports `tier={smoke,representative,full}` and `corpus=<id>|all`.

For each selected corpus, CI:

1. builds `middens` from source;
2. materializes the pinned HF JSONL corpus into `.tmp/hf-corpora/<id>`;
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
7. uploads the flat technique output, notebook, and manifest as CI artifacts.

No `middens interpret` or `middens run --model ...` step is used.

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

Smoke result: 7 sessions parsed, 23/23 techniques completed, export succeeded, manifest had 23 technique entries.

## Caveats / next steps

- The registry is repo-local for now. If we want a first-class Hugging Face *dataset of corpus definitions*, publish this JSON registry (and optionally derived manifests) to HF and have CI download the registry from there.
- Several public candidate datasets are duplicate-shaped (`*-pi-mono`). Keep them separate for CI coverage, but do not count them as independent scientific replication without deduplication.
- Parquet trace datasets need a real streaming/schema-aware normalizer before joining the full-analysis CI path.
- Weekly `full` runs may hit HF unauthenticated rate limits; add `HF_TOKEN` as a repo secret if that becomes noisy.
