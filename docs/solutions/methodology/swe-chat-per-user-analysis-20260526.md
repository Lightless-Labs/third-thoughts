---
title: "SWE-chat per-user aggregate analysis"
module: third-thoughts
date: 2026-05-26
problem_type: methodology
component: public-hf-corpus-analysis
severity: medium
status: preliminary
tags:
  - huggingface
  - swe-chat
  - per-user-analysis
  - gated-dataset
  - privacy
---

# SWE-chat per-user aggregate analysis

## What we were trying to figure out

User asked whether and how to run a full per-user analysis on the latest HF corpus, `SALT-NLP/SWE-chat`.

Short version: yes, there is a clean per-user path. The metadata-only pass is complete, and a full 23-technique middens battery was attempted for all user groups after filtering to currently parseable/likely-parseable agents.

The key table is `sessions.parquet`, which contains:

- `session_id`
- `user_id`
- `owner_id`
- `repo_id`
- `agent`
- `transcript_path`
- token/tool/turn/prompt counts
- code-attribution metrics (`agent_percentage`, `agent_lines`, human added/modified/removed)
- outcome-ish fields (`user_persona`, `session_success`)

That means there are two viable levels of per-user analysis:

1. **Metadata-only per-user aggregate analysis** — fast, no raw transcript text, no prompt/tool-result/diff materialization. This is what we ran first.
2. **Full middens battery per user** — group transcripts by `user_id`, materialize each group, and run `middens analyze --all` per group. This is now implemented as a resumable batch runner and has been attempted for the currently supported SWE-chat agents.

## Privacy posture

The SWE-chat README says user prompts and assistant text responses were redacted with Microsoft Presidio and TruffleHog. Good! Still not a blank cheque: the dataset also includes thinking traces, tool results, code changes, repository metadata, and commit tables. The metadata-only pass avoids raw transcript text entirely and hashes `user_id`, `repo_id`, and `owner_id` before writing output.

Raw gated downloads/caches from smoke tests were deleted after use. The local analysis artifacts are under gitignored `experiments/swe-chat-per-user/`.

## Implementation

Dataset-specific adapter:

- `scripts/hf_dataset_adapters.py` (`SweChatAdapter`) owns the SWE-chat contract: metadata tables come from Parquet, raw transcripts live at `transcripts/{session_id}.jsonl`, and `sessions.transcript_path` is treated as provenance/fallback rather than generic truth.

Metadata script:

```bash
HF_TOKEN=... python3 scripts/analyze_swe_chat_per_user.py --force
```

Middens batch runner:

```bash
HF_TOKEN=... python3 scripts/run_swe_chat_per_user_middens.py \
  --force \
  --include-missing-user \
  --agents 'Claude Code,claude-code,Codex' \
  --skip-missing-transcripts \
  --command-timeout 3600 \
  --timeout 1800
```

Metadata outputs:

- `experiments/swe-chat-per-user/summary.json`
- `experiments/swe-chat-per-user/per_user.json`
- `experiments/swe-chat-per-user/per_user_summary.csv`
- `experiments/swe-chat-per-user/report.md`

Middens batch outputs:

- `experiments/swe-chat-per-user-middens/plan.json`
- `experiments/swe-chat-per-user-middens/batch_state.json`
- `experiments/swe-chat-per-user-middens/batch_summary.csv`
- `experiments/swe-chat-per-user-middens/batch_summary_with_reasons.csv`
- `experiments/swe-chat-per-user-middens/report.md`
- one derived middens output directory per completed user group

The metadata script downloads only:

- `sessions.parquet`
- `repositories.parquet`

It writes no raw prompts, assistant text, tool results, diffs, transcript paths, or unhashed user/repo/owner IDs.

The middens batch runner does download raw transcripts, but only under `.tmp/`, deletes each user's materialized corpus after that user's run, and the raw HF cache was deleted after the batch. Only derived middens outputs remain under gitignored `experiments/`.

## Results from the first full metadata pass

Pinned revision: `SALT-NLP/SWE-chat@f66cca95b14caaa4177f7ed5eaa424608dadcffa`

| Metric | Value |
|---|---:|
| Sessions | 5,851 |
| User groups | 190 |
| Sessions with missing `user_id` | 1,943 |
| Repositories | 201 |
| Owners | 180 |
| Median sessions per user group | 6 |
| Mean sessions per user group | 30.8 |
| Max sessions in one user group | 1,943 (`missing_user`) |

Agent mix:

| Agent | Sessions |
|---|---:|
| Claude Code | 4,852 |
| OpenCode | 623 |
| Codex | 213 |
| Gemini CLI | 59 |
| unknown | 52 |
| Agent | 24 |
| Cursor | 19 |
| Roger Roger Agent | 4 |
| Copilot CLI | 2 |
| Vogon Agent | 1 |
| opencode | 1 |
| claude-code | 1 |

The biggest methodological wrinkle is the `missing_user` bucket: 1,943 sessions (33.2%) have no `user_id`. Per-user findings must either:

- report `missing_user` separately;
- use `owner_id` as a secondary axis;
- or restrict user-level claims to non-missing `user_id` rows.

Do not blend `missing_user` into a normal user denominator. We have done that movie before; the ending was denominators wearing fake moustaches.

## Full middens battery attempt

The first naive all-agent attempt immediately exposed two practical problems:

1. `sessions.transcript_path` is often the original agent-local path (`.claude/projects/...`), not the HF repo path. The runner now uses the canonical README path `transcripts/{session_id}.jsonl` and only falls back to `transcript_path` for future schema variants.
2. Not all SWE-chat agents are supported by current middens parsers. OpenCode/Gemini/Cursor/Copilot-style traces need parser or normalizer work. The completed batch therefore filtered to `Claude Code`, `claude-code`, and `Codex`.

Batch outcome:

| Metric | Value |
|---|---:|
| Selected user groups | 175 |
| Selected sessions | 5,066 |
| Completed groups | 165 |
| Failed groups | 10 |
| Completed group sessions | 4,999 |
| Failed group sessions | 67 |
| Materialized files in completed groups | 4,998 |
| Skipped transcript 404s | 1 |

Every completed group has 23 technique entries and zero technique errors in its manifest.

Failure reasons:

| Reason | Groups |
|---|---:|
| No supported parser matched after materialization | 7 |
| Storage PII column-name blocklist tripped by MCP tool names containing `content` | 3 |

Largest completed groups:

| User group | Sessions | Materialized files | Wall time |
|---|---:|---:|---:|
| `missing_user` | 1,773 | 1,772 | 2,403s |
| `user_679d038e1b552cb2` | 450 | 450 | 300s |
| `user_8322e1d4eaa250c8` | 265 | 265 | 143s |
| `user_e551aeb83d84d70f` | 206 | 206 | 115s |
| `user_ac3038bf9270df66` | 144 | 144 | 143s |

Important scope note: this is **not all-agent SWE-chat coverage**. It is full 23-technique per-user coverage for the subset selected as current-parser-compatible, plus explicit failures where that assumption was wrong.

## Current status

- Metadata-only full per-user analysis: **done**.
- Three-transcript gated parser smoke: **done** (`middens analyze --split --no-python`, all 3 parsed as subagent).
- Full 23-technique per-user battery for currently supported/likely-supported agents: **attempted and mostly completed** (165/175 groups, 4,999/5,066 selected sessions).
- Remaining work: parser/normalizer support for all SWE-chat agent formats and a fix/escape hatch for tool-name-derived columns that trip the storage PII blocklist.
