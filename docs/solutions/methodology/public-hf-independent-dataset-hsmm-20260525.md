---
title: "Independent HSMM summaries for public Hugging Face candidate datasets"
module: third-thoughts
date: 2026-05-25
problem_type: methodology
component: hsmm-replication
severity: medium
status: completed
tags:
  - hsmm
  - huggingface
  - public-datasets
  - stratification
  - reproducibility
---

# Independent HSMM summaries for public Hugging Face candidate datasets

## Why this exists

The first fixed public HF HSMM pass used the seed datasets conservatively: it built one primary fixed cohort and excluded discovery-list candidates from the headline. That was too binary. Not mixing heterogeneous/test/synthetic/personal datasets into one behavioural headline is good; not analyzing them at all is just leaving data on the table, looking very pleased with ourselves while doing it.

So this pass analyzes each public candidate dataset independently and reports separate aggregate results. No cross-dataset pooling, no transcript snippets, no privacy victory laps.

Builder/runner: `scripts/run_public_hf_independent_hsmm.py`.

Gitignored artifacts: `experiments/hsmm-public-hf-independent/`.

## Scope

Datasets covered:

- user-seeded datasets;
- `other=pi-share-hf` candidates observed on 2026-05-23;
- `search=claude code` candidates observed on 2026-05-23.

Each dataset revision is pinned in the runner. Object-level SHA-256, parser status, and normalized session artifacts are recorded in the gitignored experiment directory.

## Results

| Dataset | Source | Status | Sessions | Assistant turns | Corrections | Tool calls | HSMM lift | States | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `cfahlgren1/agent-sessions-list` | seed | insufficient_data | 7 | 337 | 10 | 299 | — | — | mixed Claude/Codex/Pi sanity cohort |
| `badlogicgames/pi-mono` | seed/pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | main public Pi cohort |
| `armand0e/badlogicgames-pi-mono-opus-filtered` | seed | hsmm_complete | 182 | 4,082 | 159 | 4,243 | 6.04× | 4 | filtered derivative/cross-check |
| `archit11/claude-code-traces` | seed/claude-code-search | hsmm_complete | 25 | 215 | 0 | 190 | 0.00× | 5 | Parquet request/response traces |
| `LarsEckart/approvaltests-java-sessions` | other=pi-share-hf | insufficient_data | 7 | 519 | 5 | 547 | — | — | — |
| `thomasmustier/pi-for-excel-sessions` | other=pi-share-hf | hsmm_complete | 161 | 43,740 | 348 | 44,095 | 7.86× | 5 | — |
| `thomasmustier/pi-nes-sessions` | other=pi-share-hf | model_unstable | 11 | 415 | 14 | 398 | — | — | HMM fit reported too uniform/sparse |
| `JohnBeanerson/pi-mono-test` | other=pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | test-looking dataset; analyzed separately only |
| `karkowww/pi-mono` | other=pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | duplicate-shaped Pi mono cohort |
| `Prayagmatic/agent-traces` | other=pi-share-hf | hsmm_complete | 55 | 906 | 22 | 1,037 | 5.15× | 5 | — |
| `julien-c/pi-sessions` | other=pi-share-hf | hsmm_complete | 17 | 425 | 4 | 346 | 5.59× | 5 | — |
| `invincible-jha/pi-mono` | other=pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | duplicate-shaped Pi mono cohort |
| `aaaaliou/pi-mono` | other=pi-share-hf | hsmm_complete | 145 | 4,516 | 171 | 4,699 | 1.44× | 5 | — |
| `aaaaliou/pi-playdate` | other=pi-share-hf | insufficient_data | 1 | 476 | 9 | 532 | — | — | — |
| `aaaaliou/playdate-games` | other=pi-share-hf | insufficient_data | 4 | 671 | 29 | 816 | — | — | — |
| `aaaaliou/pi-synthetic` | other=pi-share-hf | hsmm_complete | 38 | 1,338 | 69 | 1,450 | 6.48× | 4 | synthetic-looking dataset; analyzed separately only |
| `assafvayner/pi-mono` | other=pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | duplicate-shaped Pi mono cohort |
| `kaofelix/video-scissors-sessions` | other=pi-share-hf | hsmm_complete | 14 | 2,142 | 51 | 2,107 | 2.32× | 5 | — |
| `aaaaliou/pi-sessions-viewer` | other=pi-share-hf | insufficient_data | 5 | 288 | 13 | 270 | — | — | — |
| `thomasmustier/pi-mono-sessions` | other=pi-share-hf | hsmm_complete | 103 | 1,636 | 44 | 1,387 | 4.02× | 5 | — |
| `thomasmustier/pi-extensions-sessions` | other=pi-share-hf | hsmm_complete | 113 | 5,757 | 193 | 5,274 | 6.17× | 5 | — |
| `thomasmustier/economist-tui-sessions` | other=pi-share-hf | insufficient_data | 8 | 692 | 14 | 654 | — | — | — |
| `thomasmustier/clean-slides-sessions` | other=pi-share-hf | hsmm_complete | 11 | 1,294 | 9 | 1,265 | 10.11× | 5 | very small n; treat as descriptive |
| `deepflame-bot/pi-publish` | other=pi-share-hf | insufficient_data | 1 | 1,955 | 6 | 2,215 | — | — | — |
| `Ev3lynx727/pi-cavelynx` | other=pi-share-hf | insufficient_data | 2 | 573 | 6 | 504 | — | — | — |
| `grfwings/pi-session-traces` | other=pi-share-hf | insufficient_data | 1 | 132 | 3 | 111 | — | — | — |
| `bhollmann/pi-mono` | other=pi-share-hf | hsmm_complete | 626 | 15,605 | 630 | 15,439 | 5.61× | 5 | duplicate-shaped Pi mono cohort |
| `armand0e/kimi-k2.6-claude-code-traces` | search=claude code | hsmm_complete | 36 | 5,164 | 4 | 1,631 | 1.89× | 4 | Claude-Code-style JSONL traces |
| `archit11/claude_code_traces_hs` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | unsupported Parquet schema for current normalizer |
| `archit11/claude_code_traces_dirty` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | unsupported Parquet schema for current normalizer |
| `nlile/misc-merged-claude-code-traces-v1` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | unsupported Parquet schema for current normalizer |
| `misterkerns/my-personal-claude-code-data` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | public personal data; current parser yielded no normalized sessions |
| `REXX-NEW/my-personal-claude-code-data` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | public personal data; current parser yielded no normalized sessions |
| `JohnBeanerson/claude-code-sessions-test` | search=claude code | no_parseable_sessions | 0 | 0 | 0 | 0 | — | — | test dataset; current parser yielded no normalized sessions |
| `ultralazr/claude-code-traces` | search=claude code | insufficient_data | 1 | 297 | 15 | 116 | — | — | — |
| `gabegoodhart/traces.claude-code.mlx-lm-granitemoehybrid` | search=claude code | insufficient_data | 1 | 219 | 0 | 127 | — | — | model-specific trace derivative |

## Quick read

- 19 datasets produced complete current-middens HSMM results.
- 11 datasets were too small for HSMM fitting under the current technique guardrails.
- 1 dataset was parseable but too uniform/sparse for stable HMM fitting.
- 6 datasets need additional normalizers or parser support before HSMM is meaningful.
- Several `*-pi-mono` repos appear duplicate-shaped: same session/turn/correction/tool totals and same 5.61× HSMM lift. They should stay separate in the independent table, but should not be counted as independent replication evidence without deduplication.

## Caveats

- This is current `middens/python/techniques/hsmm.py` only, not the legacy HSMM script.
- `insufficient_data` means the technique refused to fit; it is not evidence of no signal.
- Parquet trace datasets need schema-specific/streaming normalizers beyond the first `conversation_json` request/response adapter.
- Public datasets are not treated as privacy-safe; no transcript content is reproduced here.

## Methodological conclusion

Analyzing the shared public datasets independently strengthens the qualitative picture: among datasets where HSMM fits, a pre-correction/pre-failure lift often appears, but magnitude varies materially by dataset family. That supports the current project stance: **direction replicated; magnitude unstable; do not collapse this into one shiny headline number.**
