---
title: "Comparative public corpus metrics and interpretation"
status: in_progress
priority: P1
tags: [comparative-analysis, public-results, interpretation, methodology]
source: public-results-website-pipeline
---

## Why

Per-corpus reports are useful, but the website also needs an honest cross-corpus view: which findings replicate, which are dataset-family-specific, which are missing because a stratum/axis is absent, and which are too unstable to headline.

The comparative layer must operate over curated `metrics.json` bundles, not raw outputs.

## What

Add deterministic comparative aggregation first:

```bash
scripts/build_public_comparative_metrics.py \
  --corpora-dir site-data/corpora \
  --output site-data/comparative
```

Outputs:

```text
site-data/comparative/
  corpus-index.json
  comparative-metrics.json
  technique-status-matrix.json
  finding-replication-matrix.json
```

Then add optional comparative interpretation:

```bash
scripts/interpret_public_comparison.py \
  --comparative-dir site-data/comparative \
  --prompt docs/prompts/public-comparative-interpretation-v1.md \
  --model <model>
```

The deterministic layer should include:

- corpus counts and source families;
- duplicate/subset warnings;
- stratum coverage matrix;
- technique completion matrix;
- selected metric ranges by corpus/stratum;
- robust/provisional/not-tested classification inputs;
- explicit `N=0` and insufficient-data flags.

The LLM layer should produce categories like:

- robust across selected corpora;
- replicated but magnitude-variable;
- provisional;
- contradicted;
- not tested;
- blocked by missing stratum/language/thinking-visibility axis.

## Done

- [x] Deterministic comparative metrics script exists.
- [x] Comparative output never pools duplicate-shaped corpora as independent evidence without a warning.
- [x] Missing autonomous/language/thinking-visibility axes are explicit.
- [ ] Comparative interpretation prompt exists and is reviewed.
- [x] Website renders comparative metrics. Interpretation remains pending.
- [ ] Comparative interpretation reruns only when input/process fingerprints change.

## Progress notes

2026-05-29 deterministic half complete. Implementation: `scripts/build_public_comparative_metrics.py`; tests: `tests/test_build_public_comparative_metrics.py`; methodology: `docs/solutions/methodology/public-comparative-metrics-20260529.md`; plan: `docs/plans/2026-05-29-003-feat-public-comparative-metrics-plan.md`.

The script writes `corpus-index.json`, `comparative-metrics.json`, `technique-status-matrix.json`, and `finding-replication-matrix.json` under `site-data/comparative/`. `scripts/build_public_results_site.py` renders the comparative JSON when present, and the HF CI workflow builds comparative metrics before building/deploying the site. LLM comparative interpretation is intentionally still pending until prompt/fingerprint work lands.
