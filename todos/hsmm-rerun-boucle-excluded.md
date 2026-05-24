---
title: "Re-run HSMM pre-failure analysis with Boucle-contaminated windows excluded"
status: todo
priority: P1
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

## Done

- [ ] Exclusion criteria are explicit and reproducible.
- [ ] Session counts before/after W10–W12 Boucle exclusion are recorded.
- [ ] HSMM re-run completes or a clear blocker is documented.
- [ ] Results are stratified rather than mixed.
- [ ] Output artifacts are written under `experiments/` and not committed.
- [ ] The HSMM finding status is updated in `docs/HANDOFF.md`.
- [ ] Any required methodology solution doc is added or updated.

## References

- `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`
- `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md`
- `docs/HANDOFF.md`
- `todos/autonomous-session-stratum.md`
