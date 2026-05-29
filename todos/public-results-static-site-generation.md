---
title: "Generate and deploy public corpus results website"
status: todo
priority: P1
tags: [website, github-pages, public-results, ci]
source: public-results-website-pipeline
---

## Why

GitHub Pages currently has a hand-built initial cut. Public corpus results need a generated site so new corpus analyses, split counts, and comparative metrics can be published repeatably without manual HTML edits.

## What

Add a static site generator, likely:

```bash
scripts/build_public_results_site.py \
  --site-data site-data \
  --output site-out
```

Inputs:

- `site-data/corpora/*/metrics.json`
- optional per-corpus `interpretation.md`
- comparative metrics / interpretation bundles
- templates or lightweight inline HTML builders

Outputs:

```text
site-out/
  index.html
  corpora/index.html
  corpora/<corpus-id>/index.html
  comparative/index.html
  methodology/index.html
  downloads/index.html
  assets/...
```

Pages should show:

- corpus cards with provenance and pinned revisions;
- session and stratum counts;
- technique completion matrix;
- key public-safe metrics;
- caveats for missing language/autonomous/thinking-visibility axes;
- links to notebooks only if explicitly publish-enabled;
- process/model/prompt fingerprints when interpretation is present.

## Deployment

Either:

- keep using the existing `www` orphan branch and push generated files there; or
- migrate to GitHub Pages artifacts/actions.

Use the existing `www` branch for the first cut unless there is a strong reason to migrate.

## Done

- [ ] Site generator builds pages from `site-data` without network access.
- [ ] Generated site includes corpus index, per-corpus pages, comparative page, and methodology/provenance page.
- [ ] GitHub Actions deploys generated output to Pages on trusted runs.
- [ ] PR runs can build the site without deploying.
- [ ] No raw analysis artifacts are published unless explicitly allowlisted.
