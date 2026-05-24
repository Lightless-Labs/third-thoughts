---
title: "Build a fixed public Hugging Face agent-session cohort for HSMM replication"
status: done
priority: P1
completed: 2026-05-24
tags: [research, hsmm, reproducibility, huggingface, corpus, privacy, secrets]
source: user-direction-2026-05-23
---

## Why

The HSMM re-run must not depend on whatever local Claude/Pi/Codex logs still happen to exist today. Local agent logs are live, symlinked, and subject to pruning. Comparing an old 24.6× result to a new run on a different moving corpus is not replication; it is numerology with better fonts.

Use a fixed, public Hugging Face cohort instead. Pin dataset revisions, hash every raw JSONL / Parquet / source object, and run both HSMM implementations on the same materialized cohort.

## Start here next session

1. Read this todo and `todos/hsmm-rerun-boucle-excluded.md`.
2. Build the fixed HF cohort manifest first; do **not** start by running HSMM on local `corpus-full/` or `corpus-split/`.
3. Normalize accepted source formats into a common `Session[]` shape, with unsupported schemas recorded explicitly.
4. Run HSMM only after the cohort is pinned, hashed, and materialized.

Important: ad-hoc smoke checks from 2026-05-23 are **not findings**. They were:

- current `middens/python/techniques/hsmm.py`, non-fixed 200-session samples: baseline 1.25×, Boucle-excluded 3.13×;
- legacy `scripts/hsmm_behavioral_states.py`, filtered corpus attempt: loaded only 29 sessions and reported insufficient correction data;
- full `middens analyze --techniques hsmm` on a local filtered corpus timed out before producing usable output.

Treat those only as pipeline diagnostics. The publishable result starts with this fixed public cohort.

## Candidate public datasets

Seed datasets supplied by the user:

| Dataset | Purpose | Revision observed 2026-05-23 |
|---|---|---|
| `cfahlgren1/agent-sessions-list` | small mixed-source sanity cohort: Claude, Codex, Pi | `10d6d295cb79a11194cfd93f0e9752b76889fbba` |
| `badlogicgames/pi-mono` | main public Pi cohort | `dac2a1d3ba12dda597b973a791a77618ccb5f413` |
| `armand0e/badlogicgames-pi-mono-opus-filtered` | filtered Pi cohort / cross-check | `32e67a8d04febcb38a2d28798a6d80fb41481a38` |
| `archit11/claude-code-traces` | Claude Code trace cohort; Parquet, not raw JSONL | `416248040ba2c706c475bba238782c3e334fd4d8` |
| Hugging Face search: `pi session` | discovery source for additional public Pi datasets | pin exact repo revisions before use |
| Hugging Face filter: `other=pi-share-hf` | discovery source for datasets published with pi-share-hf metadata | pin exact repo revisions before use |
| Hugging Face search: `claude code` | discovery source for public Claude Code trace/session datasets | pin exact repo revisions before use |

Do not silently float to dataset `main`; use pinned revisions or record the exact revision in the manifest.

As of 2026-05-23, the `other=pi-share-hf` filter returned these candidate datasets/revisions:

| Dataset | Revision observed 2026-05-23 |
|---|---|
| `badlogicgames/pi-mono` | `dac2a1d3ba12dda597b973a791a77618ccb5f413` |
| `LarsEckart/approvaltests-java-sessions` | `8713a8d6eff46c759be66f1d37c306f30c8cdaa6` |
| `thomasmustier/pi-for-excel-sessions` | `1b7218d2acf621e52bb5208435b1f80154342e3f` |
| `thomasmustier/pi-nes-sessions` | `2189a4493f6760224f220cea1b5b2a965a528e5f` |
| `JohnBeanerson/pi-mono-test` | `3b386145073c5fb7974cd604559719059d5411a3` |
| `karkowww/pi-mono` | `0fd28f883a880ad2b67084c5ccc36bcd53fb2bc2` |
| `Prayagmatic/agent-traces` | `91106233747240a83190fc1c4135be9d4d87c386` |
| `julien-c/pi-sessions` | `700416886204bcdbca133373daed3d2504c853cf` |
| `invincible-jha/pi-mono` | `d3438c8c224205dd3ac45cce08ceb174fbfe770b` |
| `aaaaliou/pi-mono` | `61eee21d662f8736ace59507fc30555e1bff5c6e` |
| `aaaaliou/pi-playdate` | `ac113723b9642274c1f4b8f0905438f090f14dda` |
| `aaaaliou/playdate-games` | `19d22b5be8a48d42e30bd44bca58d62c240f5171` |
| `aaaaliou/pi-synthetic` | `f962b816f0c1637ef23ffe11019fab0591ff1ad9` |
| `assafvayner/pi-mono` | `bf64b2a4fc16ce98cc76c842ce046b01b6c688c1` |
| `kaofelix/video-scissors-sessions` | `17a9da24e81fa15e6d0b271b77152c333d52d3ed` |
| `aaaaliou/pi-sessions-viewer` | `d13e1e9ba4a8b1310dd67c1d12b29d40c6705b5f` |
| `thomasmustier/pi-mono-sessions` | `b6e68ac0e8d9f53de96aa4a6f0ff630a53bb8cae` |
| `thomasmustier/pi-extensions-sessions` | `ae6f02c5fd581a49ac1e9bbedbb65c3300a985b7` |
| `thomasmustier/economist-tui-sessions` | `3ffcea7e16c44f83efd9fad42a4cdf73ce725f9f` |
| `thomasmustier/clean-slides-sessions` | `ccab758ba8f6ccc7bfa5ef6d628e531125a1e0a6` |
| `deepflame-bot/pi-publish` | `241968f75241fe8ecb29662e2ef0ceb7d1af4161` |
| `Ev3lynx727/pi-cavelynx` | `1478da03d0d8f2fa3fb3bc63f4fe4287e268fd12` |
| `grfwings/pi-session-traces` | `bdb8de4ea0affd5d1a1e4d69df2bebc473447602` |
| `bhollmann/pi-mono` | `9101a5388ff8234b05e9f7e934c4699ae407f603` |

These are discovery candidates, not automatic inclusions. First pass should filter out obvious tests/synthetic datasets unless the goal is parser validation rather than behavioural inference.

As of 2026-05-23, `search=claude code` returned these especially relevant candidates/revisions:

| Dataset | Revision observed 2026-05-23 | Note |
|---|---|---|
| `archit11/claude-code-traces` | `416248040ba2c706c475bba238782c3e334fd4d8` | `data/train-00000-of-00001.parquet`; likely needs a Parquet-to-session normalization adapter. |
| `armand0e/kimi-k2.6-claude-code-traces` | `1f02263eb3c1d41f9d7b264baf56a09063a67963` | Claude-Code-style traces, model-specific derivative candidate. |
| `archit11/claude_code_traces_hs` | `b47770a9ec552c82dddcf6b1d79acc5247c1e3d2` | Related Claude Code trace cohort. |
| `archit11/claude_code_traces_dirty` | `fb7eaf68f1f2960101baa54b35d5369970ddde26` | Dirty trace cohort; likely useful for parser robustness, not first-pass inference. |
| `nlile/misc-merged-claude-code-traces-v1` | `ab456b000b13563156e84d75bfa4d20acccb4f88` | Merged traces; inspect schema/provenance before inclusion. |
| `misterkerns/my-personal-claude-code-data` | `e6aff5fa4941ef1cbfcbca7bf09ac04506d22691` | Public personal session data; inspect privacy/provenance. |
| `REXX-NEW/my-personal-claude-code-data` | `33780c77b955a844c9c1be2f00801def0d407c45` | Public personal session data; inspect privacy/provenance. |
| `JohnBeanerson/claude-code-sessions-test` | `3904ff701d06c18699ae167932c4cd02ce3647a0` | Test dataset; parser validation candidate, not behavioural inference. |
| `ultralazr/claude-code-traces` | `afe3c108c148427625f7b2275791517f99f8115d` | Trace cohort candidate. |
| `gabegoodhart/traces.claude-code.mlx-lm-granitemoehybrid` | `8717352ccbf29731901ed6f00282cb4ce64bffe0` | Trace cohort candidate, likely model-specific. |

## Privacy / secret-screening note

Use `badlogic/pi-share-hf` as the reference for public-session hygiene before treating public datasets as safe enough for analysis artifacts:

- repo revision observed 2026-05-23: `21c1d9629187b553a2d59f26c5ef28eb33bb4e70`
- deterministic redaction handles exact secret values from `--env-file` / `--secret`;
- user deny patterns are applied via `--deny`;
- TruffleHog scans redacted output with `--results=verified,unknown,unverified`;
- **any** TruffleHog finding blocks publication;
- LLM review checks project relevance, shareability, and missed sensitive data.

For our cohort: do not claim the datasets are privacy-safe merely because they are public. Record whether a dataset documents pi-share-hf or equivalent screening. Avoid committing raw transcripts or derived snippets that include private paths/secrets.

## What

Create a reproducible public cohort manifest and materialization for HSMM replication. Expect more than one format: Pi datasets are mostly raw JSONL session files, while at least one Claude Code trace dataset (`archit11/claude-code-traces`) is Parquet. The first implementation task is therefore a normalization layer that can turn each accepted source format into the common `Session[]` shape used by `middens` techniques and, where possible, raw/session-like files for legacy scripts.

Minimum manifest fields per source object:

- `dataset_repo`
- `dataset_revision`
- `repo_path`
- `storage_format` (`jsonl`, `parquet`, `json`, or other observed format)
- `sha256`
- `size_bytes`
- `source_tool` if inferable
- first timestamp / ISO week if inferable
- parser / normalizer status
- contamination flags if applicable (`queue_operation`, `boucle_marker`, `zero_tool_session`, `w10_w12`)
- inclusion flags for each analysis cohort

Cohorts:

1. `public_hf_baseline_fixed` — all eligible parseable sessions from the pinned public datasets.
2. `public_hf_boucle_excluded_fixed` — same cohort minus explicit Boucle/autonomous contamination, if present.
3. Optional source-specific cohorts (`pi_only`, `mixed_source`) if mixed parser/source behavior makes the headline too muddy.

## How

1. Use `huggingface_hub` / `snapshot_download` with pinned revisions.
2. Store raw snapshots under `experiments/hsmm-public-hf-fixed/raw/` or another gitignored experiment path.
3. Write a manifest under `experiments/hsmm-public-hf-fixed/manifest.jsonl`.
4. Inspect schemas for each dataset family before inclusion:
   - Pi raw JSONL / `pi-share-hf` layout;
   - Claude Code raw JSONL if present;
   - Parquet trace rows such as `archit11/claude-code-traces`.
5. Add/choose normalizers per format rather than coercing silently. If a dataset cannot be normalized with clear semantics, mark it `unsupported_schema` in the manifest and exclude it from inference.
6. Materialize cohort directories with symlinks/copies for legacy scripts where the raw format is compatible.
7. Produce parsed/normalized `Session[]` JSON for the current `middens/python/techniques/hsmm.py` implementation.
8. Run both implementations on both fixed cohorts:

   | Implementation | Baseline fixed | Boucle-excluded fixed |
   |---|---:|---:|
   | `scripts/hsmm_behavioral_states.py` | run | run |
   | `middens/python/techniques/hsmm.py` | run | run |

7. Compare only within the same implementation.

## Completion notes (2026-05-24)

Implemented `scripts/build_public_hf_hsmm_cohort.py` and materialized the fixed cohort under gitignored `experiments/hsmm-public-hf-fixed/`.

Pinned primary inference datasets:

- `cfahlgren1/agent-sessions-list@10d6d295cb79a11194cfd93f0e9752b76889fbba`
- `badlogicgames/pi-mono@dac2a1d3ba12dda597b973a791a77618ccb5f413`

Pinned but excluded from headline inference:

- `armand0e/badlogicgames-pi-mono-opus-filtered@32e67a8d04febcb38a2d28798a6d80fb41481a38` — derivative/cross-check only.
- `archit11/claude-code-traces@416248040ba2c706c475bba238782c3e334fd4d8` — Parquet request/response traces normalized separately, excluded from HSMM inference because they are not durable session logs.

Generated aggregate counts:

| Cohort | Sessions | Legacy JSONL files | Assistant turns | Tool calls | Corrections |
|---|---:|---:|---:|---:|---:|
| `public_hf_baseline_fixed` | 633 | 633 | 15,942 | 15,738 | 640 |
| `public_hf_boucle_excluded_fixed` | 622 | 622 | 15,913 | 15,725 | 640 |
| `crosscheck_filtered_pi` | 182 | 182 | 4,082 | 4,243 | 159 |

Manifest status: 825 object rows, 815 parseable JSONL transcript files, 1 normalized Parquet trace object, 9 metadata objects excluded. The manifest records SHA-256, size, parser/normalizer status, contamination flags, inclusion flags, and lightweight secret-screening provenance. This is not equivalent to TruffleHog; public data is still treated as not-safe-to-commit.

Sanitized methodology summary: `docs/solutions/methodology/fixed-public-hf-hsmm-rerun-20260524.md`.

## Done

- [x] Dataset revisions are pinned and recorded.
- [x] Raw object SHA-256 hashes are recorded for JSONL, Parquet, and any other accepted source format.
- [x] Source schemas are inspected and normalization status is recorded.
- [x] Cohort inclusion/exclusion criteria are explicit.
- [x] Manifest and generated outputs live under `experiments/` and are not committed.
- [x] Both HSMM implementations run on the same fixed materialized cohort(s); the legacy script's extra sampling/filtering caveat is documented.
- [x] Results are summarized without leaking transcript contents.
- [x] `todos/hsmm-rerun-boucle-excluded.md` and `docs/HANDOFF.md` are updated with the actual fixed-cohort results.

## References

- `todos/hsmm-rerun-boucle-excluded.md`
- `https://huggingface.co/datasets/cfahlgren1/agent-sessions-list`
- `https://huggingface.co/datasets/badlogicgames/pi-mono`
- `https://huggingface.co/datasets/armand0e/badlogicgames-pi-mono-opus-filtered`
- `https://huggingface.co/datasets/archit11/claude-code-traces`
- `https://huggingface.co/datasets?search=pi%20session`
- `https://huggingface.co/datasets?other=pi-share-hf`
- `https://huggingface.co/datasets?search=claude%20code`
- `https://github.com/badlogic/pi-share-hf`
