# Publishing public corpus results

This is the operator guide for updating the public results website at:

<https://lightless-labs.github.io/third-thoughts/>

The short version: **run the HF Corpus Analysis workflow manually**. It materializes pinned public corpora, runs `middens`, extracts public-safe metrics, builds comparative metrics, generates the static site, and deploys to the existing `www` branch on trusted non-PR runs. No raw transcripts are published unless somebody deliberately breaks the rules, which would be rude.

## What gets published

The website is generated from curated `site-data`, not raw analysis outputs.

Per corpus, the pipeline publishes only:

```text
site-data/corpora/<id>/
  corpus.json
  analysis-manifest.json
  split-manifest.json
  metrics.json
  fingerprints.json
  status.json
```

Comparative outputs:

```text
site-data/comparative/
  corpus-index.json
  comparative-metrics.json
  technique-status-matrix.json
  finding-replication-matrix.json
```

The generated site is written to `site-out/` in CI and force-pushed to the `www` branch root when deployment is allowed.

## What must not be published

Do **not** publish:

- raw transcripts;
- prompts, assistant text, thinking text, or tool payloads;
- raw per-session tables;
- session ids;
- source paths, project names, or local absolute paths;
- notebooks or Parquet files unless a future allowlist explicitly permits them.

The relevant safety docs are:

- `docs/solutions/methodology/public-results-metrics-allowlist-20260529.md`
- `docs/solutions/methodology/public-comparative-metrics-20260529.md`

## Publish from GitHub Actions

Workflow: `.github/workflows/hf-corpus-analysis.yml`

### Using the GitHub UI

1. Open GitHub → **Actions** → **HF Corpus Analysis**.
2. Click **Run workflow**.
3. Choose inputs:
   - `tier`: `smoke`, `representative`, or `full`;
   - `corpus`: a specific corpus id or `all`;
   - `registry_repo`: usually blank unless using a published HF registry dataset;
   - `registry_revision`: usually `main` when `registry_repo` is set;
   - `force`: leave `false` to reuse unchanged published bundles, set `true` to rerun everything.
4. Start the run.
5. Wait for all matrix jobs and the `Build public results site` job.
6. On success, the workflow pushes generated output to the `www` branch.
7. Check <https://lightless-labs.github.io/third-thoughts/> after Pages catches up.

Recommended normal publication run:

```text
tier=full
corpus=all
registry_repo=
registry_revision=main
```

Fast smoke/deploy sanity run:

```text
tier=smoke
corpus=all
registry_repo=
registry_revision=main
```

### Using `gh`

```bash
gh workflow run hf-corpus-analysis.yml \
  -f tier=full \
  -f corpus=all \
  -f registry_repo= \
  -f registry_revision=main
```

Watch the run:

```bash
gh run list --workflow hf-corpus-analysis.yml --limit 5
gh run watch <run-id>
```

If you need to publish only one corpus:

```bash
gh workflow run hf-corpus-analysis.yml \
  -f tier=full \
  -f corpus=badlogicgames-pi-mono \
  -f registry_repo= \
  -f registry_revision=main
```

## Fingerprint reuse

Trusted non-PR runs fetch the prior generated `www` branch bundle from `downloads/corpora/<id>/`, materialize the pinned corpus, compute current corpus/process fingerprints, and reuse the previous public-safe bundle when those fingerprints match. This skips the full `middens analyze` battery for unchanged corpora while still rebuilding comparative metrics and the static site from collected bundles.

Manual dispatch has a `force` input. Set `force=true` when you want to ignore fingerprints and rerun the analysis battery anyway (for example after suspecting a stale artifact, or because computers are doing computer things).

Each published corpus bundle includes `fingerprints.json` with:

- `corpus`: registry entry plus materialization count/hash summary;
- `process`: repo SHA, middens version, source-tree hashes, workflow/script hashes, and analysis flags;
- `interpretation`: currently records disabled/not-configured inputs until the LLM interpretation phase lands.

The fingerprint file hashes raw object details but does not publish raw transcript paths, session ids, prompts, tool payloads, or per-session rows.

## Deploy policy

The workflow deploys only when both are true:

- event is **not** `pull_request`;
- repository is `Lightless-Labs/third-thoughts`.

So:

| Event | Site built? | Site deployed? |
|---|---:|---:|
| pull request | yes | no |
| manual `workflow_dispatch` on main repo | yes | yes |
| weekly schedule on main repo | yes | yes |

The deploy step force-pushes `site-out/` to the `www` branch. This replaces the branch contents with generated output. That is intentional.

## Local reproduction

Use this for debugging the site pipeline without publishing anything.

### 1. Produce per-corpus site-data

If you already have local middens artifacts, run the extractor directly. Example shape:

```bash
python3 scripts/extract_public_corpus_metrics.py \
  --corpus-id <id> \
  --registry docs/corpora/public-hf-analysis-corpora.json \
  --analysis-output .tmp/middens-results/<id> \
  --split-output .tmp/middens-split-results/<id> \
  --analysis-dir <xdg-flat-run-dir> \
  --split-analysis-dir <xdg-split-run-dir> \
  --materialized-corpus .tmp/hf-corpora/<id> \
  --output .tmp/site-data/corpora/<id>
```

The extractor writes `fingerprints.json` automatically. To compute pre-analysis fingerprints for reuse decisions, use:

```bash
python3 scripts/public_results_fingerprint.py \
  --corpus-id <id> \
  --registry docs/corpora/public-hf-analysis-corpora.json \
  --materialized-corpus .tmp/hf-corpora/<id> \
  --output .tmp/current-fingerprints/<id>.json
```

Compare against a previous bundle with:

```bash
python3 scripts/public_results_changed.py \
  --current .tmp/current-fingerprints/<id>.json \
  --previous previous-site/downloads/corpora/<id>/fingerprints.json \
  --scope analysis
```

In normal operation CI does this for you after running `middens analyze`.

### 2. Build comparative metrics

```bash
python3 scripts/build_public_comparative_metrics.py \
  --corpora-dir .tmp/site-data/corpora \
  --output .tmp/site-data/comparative
```

### 3. Build the static site

```bash
python3 scripts/build_public_results_site.py \
  --site-data .tmp/site-data \
  --output .tmp/site-out
```

Open `.tmp/site-out/index.html` locally.

### 4. Run the privacy grep

Before publishing any locally generated site, run a sanity grep for known-bad classes of strings:

```bash
if rg -n "source_paths|tool_result|/Users|private/project|raw-session|please do the private thing" .tmp/site-out; then
  echo "Potential private/raw marker found" >&2
  exit 1
else
  echo "site output privacy grep ok"
fi
```

This grep is not a formal privacy proof. It is just a cheap tripwire. The real guardrail is the allowlist extractor.

## Adding or changing a corpus

1. Edit `docs/corpora/public-hf-analysis-corpora.json`.
2. Pin `dataset_revision` to an immutable revision SHA.
3. Set `analysis_enabled: true` only when the corpus is public and supported.
4. Choose `ci_tiers`:
   - `smoke` for tiny parser sanity checks;
   - `representative` for regular CI coverage;
   - `full` for publishable results.
5. Run or wait for `HF Corpus Analysis`.
6. Check the generated corpus page and comparative page.

Do not enable gated or sensitive corpora for public publishing until there is a durable auth/privacy story and a methodology note explaining it.

## Troubleshooting

### The workflow built but did not deploy

Check the event and repository. PRs intentionally do not deploy. Forks do not deploy.

### The deploy step failed with permissions

The workflow requires `permissions: contents: write` so it can push `www`. Confirm the workflow file still has that permission and that repository Actions settings allow GitHub Actions to write.

### Pages did not update immediately

The `www` branch may update before GitHub Pages cache catches up. Check the branch first:

```bash
git fetch origin www
git log --oneline origin/www -5
```

Then give Pages a minute. Computers: famously fast except when they are not.

### A corpus is missing from the site

Check:

1. `analysis_enabled` is true in the registry;
2. selected `tier` includes that corpus;
3. the matrix job completed;
4. the `Extract public-safe site data` step wrote `.tmp/site-data/corpora/<id>/metrics.json`;
5. the `Collect public-safe site data` step found the bundle.

### Comparative page is showing fallback only

That means `site-data/comparative/` was missing when the site generator ran. Run:

```bash
python3 scripts/build_public_comparative_metrics.py \
  --corpora-dir site-data/corpora \
  --output site-data/comparative
```

Then rebuild the site.
