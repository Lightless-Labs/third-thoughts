# Public results static site generation plan

**Created:** 2026-05-29

## Goal

Implement Phase 2 of the public results website pipeline: render the Phase 1 public-safe `site-data` bundles into a static GitHub Pages site, and wire trusted CI runs to deploy generated output to the existing `www` branch.

## Scope

- Add `scripts/build_public_results_site.py`.
- Input: `site-data/corpora/*/{metrics.json,corpus.json,status.json,analysis-manifest.json,split-manifest.json}` plus optional interpretation files in later phases.
- Output:
  - `index.html`
  - `corpora/index.html`
  - `corpora/<corpus-id>/index.html`
  - `comparative/index.html`
  - `methodology/index.html`
  - `downloads/index.html`
  - `downloads/corpora/<corpus-id>/*.json` for allowlisted Phase 1 bundle files only
  - `assets/style.css`
- Update `.github/workflows/hf-corpus-analysis.yml` so PRs build the site without deploying, while trusted scheduled/manual runs deploy generated output to `www`.
- Add fixture tests for the generator.

## Safety rules

- The site generator must not read raw analysis outputs, raw transcripts, notebooks, Parquet files, or `.tmp` by itself.
- Only already-curated Phase 1 files may be copied into downloads.
- HTML must escape all data values.
- No network access is required for site generation.
- Missing metrics should render as `—`, not `0`.

## Validation

- `python3 -m py_compile scripts/build_public_results_site.py tests/test_build_public_results_site.py`
- `python3 tests/test_build_public_results_site.py`
- Smoke against `.tmp/site-data-all` if local public-HF metric bundles are present.

## Done criteria mapping

- Site generator builds from `site-data` offline.
- Generated site includes corpus index, per-corpus pages, comparative page, methodology/provenance page, and downloads page.
- GitHub Actions builds on PRs and deploys on trusted scheduled/manual runs.
- No raw artifacts are copied; downloads are limited to public-safe JSON bundle files.
