---
title: "Fixed public Hugging Face HSMM re-run"
module: third-thoughts
date: 2026-05-24
problem_type: methodology
component: hsmm-replication
severity: high
status: completed
tags:
  - hsmm
  - huggingface
  - reproducibility
  - boucle
  - stratification
---

# Fixed public Hugging Face HSMM re-run

## Why this exists

The original HSMM headline claimed a 24.6× lift for a pre-failure / pre-correction behavioural state. The 2026-04-14 full-corpus run still pointed in the same direction, but the magnitude collapsed to 2.15×. Given the W10–W12 Boucle contamination in the private corpus, re-running on mutable local logs would mostly measure how much filesystem archaeology we accidentally did that day.

So this pass built a pinned public Hugging Face cohort first, hashed the source objects, and only then ran the two HSMM implementations.

Raw transcripts and normalized `Session[]` JSON live under gitignored `experiments/hsmm-public-hf-fixed/`; this document only records aggregate metadata and results.

## Pinned inputs

| Dataset | Revision | Inclusion |
|---|---|---|
| `cfahlgren1/agent-sessions-list` | `10d6d295cb79a11194cfd93f0e9752b76889fbba` | Primary small mixed-source sanity cohort |
| `badlogicgames/pi-mono` | `dac2a1d3ba12dda597b973a791a77618ccb5f413` | Primary public Pi cohort |
| `armand0e/badlogicgames-pi-mono-opus-filtered` | `32e67a8d04febcb38a2d28798a6d80fb41481a38` | Cross-check only; derivative of `badlogicgames/pi-mono` |
| `archit11/claude-code-traces` | `416248040ba2c706c475bba238782c3e334fd4d8` | Normalized as request/response traces, excluded from HSMM inference |

Generated manifest: `experiments/hsmm-public-hf-fixed/manifest.jsonl`.

The builder script is `scripts/build_public_hf_hsmm_cohort.py`. It downloads pinned snapshots with `huggingface_hub`, records SHA-256 and size for every JSONL/Parquet/metadata object, parses supported JSONL logs with `middens parse`, normalizes the observed Claude trace Parquet schema, and writes fixed normalized/legacy cohorts under `experiments/`.

## Object status

| Status | Count |
|---|---:|
| Parseable JSONL session objects | 815 |
| Normalized Parquet trace objects | 1 |
| Metadata objects excluded | 9 |
| Total manifest rows | 825 |

Format counts: 816 JSONL, 1 Parquet, 4 README markdown files, 4 `.gitattributes` files.

Privacy note: public does not mean safe. The builder records lightweight regex secret-screening provenance, but this is not equivalent to TruffleHog or the `pi-share-hf` publication gate. Do not commit raw transcript or normalized session artifacts.

## Cohorts

| Cohort | Sessions | Legacy JSONL files | Assistant turns | Tool calls | Corrections |
|---|---:|---:|---:|---:|---:|
| `public_hf_baseline_fixed` | 633 | 633 | 15,942 | 15,738 | 640 |
| `public_hf_boucle_excluded_fixed` | 622 | 622 | 15,913 | 15,725 | 640 |
| `crosscheck_filtered_pi` | 182 | 182 | 4,082 | 4,243 | 159 |
| `parquet_trace_rows_not_inference` | 25 | n/a | 25 | n/a | n/a |

Boucle exclusion removed 11 baseline sessions: one `queue-operation` session and ten W10–W12 zero-tool sessions. This public cohort does **not** reproduce the private corpus's W10–W12 Boucle contamination scale; that is useful to know, if a little less dramatic.

## Results: current middens HSMM

Implementation: `middens/python/techniques/hsmm.py`, run directly against normalized `Session[]` JSON.

| Cohort | Sessions | Assistant turns | Optimal states | Pre-correction lift | Dominant state |
|---|---:|---:|---:|---:|---:|
| `public_hf_baseline_fixed` | 633 | 15,942 | 4 | 3.55× | 1 |
| `public_hf_boucle_excluded_fixed` | 622 | 15,913 | 5 | 5.61× | 2 |
| `crosscheck_filtered_pi` | 182 | 4,082 | 4 | 6.04× | 1 |

Within the current middens implementation, the direction replicates. Magnitude is modest-to-medium, not the old 24.6× headline. Removing the small public-cohort Boucle slice increases lift from 3.55× to 5.61×, but does not rescue the old headline magnitude.

## Results: legacy HSMM

Implementation: `scripts/hsmm_behavioral_states.py`, run against the fixed legacy JSONL symlink directories.

Important caveat: the legacy script has its own filters (`MAX_SESSIONS=200`, `MIN_TURNS_PER_SESSION=15`, random seed 42, legacy raw-JSONL correction detection). It therefore uses the same fixed raw cohort, but not the identical session set or feature definition as current middens HSMM. Compare within implementation, not across implementations.

| Cohort | Loaded sessions | Observation vectors | Optimal states | Top pre-correction lift | Top state label |
|---|---:|---:|---:|---:|---|
| `public_hf_baseline_fixed` | 56 | 1,896 | 7 | 24.72× | `thinking+pre-correction` |
| `public_hf_boucle_excluded_fixed` | 56 | 1,832 | 7 | 41.32× | `thinking+pre-correction` |
| `crosscheck_filtered_pi` | 74 | 2,294 | 4 | 25.56× | `thinking+pre-correction` |

Within the legacy implementation, high lift persists and increases after Boucle exclusion. That result is real for this script, but the sampling/filtering/feature differences are too large to turn it into the project-wide headline.

## Compound scope

- `session_type`: mostly `Interactive`; a small Pi `Unknown` slice remains. There is still no first-class `Autonomous` stratum.
- `thinking_visibility`: mostly `Visible`, with some `Unknown` and one redacted Claude session.
- `language`: still unavailable because `Session::language` is not implemented; treat as `Unknown`.
- temporal window: pinned public data spans mostly 2026-W03 through W14; W10–W12 zero-tool contamination is excluded from the Boucle-excluded cohort.
- source/tool mix: overwhelmingly Pi Coding Agent; only a handful of non-Pi sessions are in the primary baseline.

## Methodological conclusion

The fixed public cohort supports a pre-correction / pre-failure signature, but the magnitude is implementation-sensitive. Current middens reports 5.61× on the fixed Boucle-excluded public cohort; the legacy script reports 41.32× on its filtered sample. The safe status is therefore:

> **Direction replicated; magnitude unstable. Do not cite a single 24.6×-style headline.**

The HSMM finding should remain downgraded/provisional until the implementation discrepancy is resolved or reported as a model-family sensitivity analysis.
