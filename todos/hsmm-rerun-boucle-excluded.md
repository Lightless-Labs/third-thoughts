---
title: "Re-run HSMM pre-failure analysis with Boucle-contaminated windows excluded"
status: done
priority: P1
completed: 2026-05-24
tags: [research, hsmm, boucle, stratification, methodology, replication]
source: beta4-next-step-2026-05-23
---

## Why

The original HSMM headline finding reported a 24.6× lift for a pre-failure behavioural state. The 2026-04-14 full-corpus run still replicated the direction, but the magnitude collapsed to 2.15×. That is not a rounding error; that is the data wearing a fake moustache.

The leading suspect is W10–W12 Boucle contamination in the interactive bucket: 1,820 of 1,826 sessions carried the `queue-operation` marker and had 100% zero tool calls. Any HSMM result that mixes those sessions with human-interactive sessions is methodologically suspect.

## What

Re-run the HSMM / pre-failure-state analysis with W10–W12 Boucle-contaminated sessions excluded, then update the finding status based on the result.

Minimum scope:

- Identify and exclude W10–W12 Boucle-contaminated sessions using the documented contamination markers.
- Preserve the compound scoping rule: report results by at least `session_type`, `thinking_visibility`, `language`, and temporal window where applicable.
- Compare the re-run against both prior reference points:
  - original 24.6× pre-failure lift;
  - 2026-04-14 full-corpus 2.15× lift.
- Write outputs under `experiments/{context}/` only; do not commit private corpus-derived outputs.
- Update documented finding status in `docs/HANDOFF.md` and parent/project guidance if the magnitude changes classification.

## How

This depends on the fixed public Hugging Face cohort in `todos/fixed-public-hf-agent-session-cohort.md`. Do that first. Do not run the decisive HSMM comparison on mutable local symlinked corpora.

Suggested first pass:

1. Re-read the contamination investigation:
   - `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`
   - `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md`
2. Build or load the fixed public HF cohort manifest from `todos/fixed-public-hf-agent-session-cohort.md`.
3. Locate the current HSMM technique and any scripts/notebooks that produced the 2.15× figure.
4. Build a filtered cohort or filtered manifest that excludes W10–W12 Boucle sessions without deleting source data.
5. Run HSMM on:
   - interactive excluding Boucle;
   - subagent separately, if applicable;
   - any already-available autonomous bucket separately, or explicitly document if autonomous stratum is not yet available.
6. Record:
   - dataset repos and pinned revisions;
   - raw object hashes;
   - session counts before/after filtering;
   - exclusion criteria;
   - state definitions / model parameters;
   - lift estimate and uncertainty / caveats;
   - whether the direction and magnitude replicate.
7. Update the finding table and methodology docs with the new status.

Do not cite the 2026-05-23 ad-hoc smoke checks as results. They were non-fixed pipeline diagnostics only: current HSMM sample baseline 1.25× vs Boucle-excluded 3.13×; legacy filtered attempt loaded only 29 sessions and had insufficient correction data; full local filtered `middens analyze --techniques hsmm` timed out.

## Completion notes (2026-05-24)

Re-run completed on the fixed public Hugging Face cohort built by `scripts/build_public_hf_hsmm_cohort.py`. Raw/normalized artifacts are under gitignored `experiments/hsmm-public-hf-fixed/`; sanitized write-up is `docs/solutions/methodology/fixed-public-hf-hsmm-rerun-20260524.md`.

Boucle exclusion criteria: remove any primary-baseline JSONL object with `queue-operation`, a Boucle/autonomous marker, or `iso_week in {2026-W10, 2026-W11, 2026-W12}` plus zero parsed tool calls. On the public fixed cohort this removed 11 sessions: 1 `queue-operation` session and 10 W10–W12 zero-tool sessions. The public cohort does not reproduce the private corpus's large W10–W12 Boucle contamination.

Current middens HSMM (`middens/python/techniques/hsmm.py`) results:

| Cohort | Sessions | Assistant turns | Optimal states | Pre-correction lift |
|---|---:|---:|---:|---:|
| `public_hf_baseline_fixed` | 633 | 15,942 | 4 | 3.55× |
| `public_hf_boucle_excluded_fixed` | 622 | 15,913 | 5 | 5.61× |
| `crosscheck_filtered_pi` | 182 | 4,082 | 4 | 6.04× |

Legacy HSMM (`scripts/hsmm_behavioral_states.py`) results on fixed raw symlink cohorts, with legacy filters/sampling (`MAX_SESSIONS=200`, `MIN_TURNS_PER_SESSION=15`, random seed 42):

| Cohort | Loaded sessions | Observation vectors | Optimal states | Top pre-correction lift |
|---|---:|---:|---:|---:|
| `public_hf_baseline_fixed` | 56 | 1,896 | 7 | 24.72× |
| `public_hf_boucle_excluded_fixed` | 56 | 1,832 | 7 | 41.32× |
| `crosscheck_filtered_pi` | 74 | 2,294 | 4 | 25.56× |

Conclusion: direction replicates, but magnitude is implementation-sensitive. The old 24.6× headline should remain downgraded/provisional rather than being promoted as a stable finding.

## Done

- [x] Exclusion criteria are explicit and reproducible.
- [x] Session counts before/after W10–W12 Boucle exclusion are recorded.
- [x] HSMM re-run completes or a clear blocker is documented.
- [x] Results are stratified/caveated by source/tool, thinking visibility, temporal window, and the missing language/autonomous axes.
- [x] Output artifacts are written under `experiments/` and not committed.
- [x] The HSMM finding status is updated in `docs/HANDOFF.md`.
- [x] Required methodology solution doc is added.

## References

- `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`
- `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md`
- `docs/HANDOFF.md`
- `todos/autonomous-session-stratum.md`
