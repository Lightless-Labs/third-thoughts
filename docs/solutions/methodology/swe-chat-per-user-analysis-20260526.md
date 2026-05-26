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

Short version: yes, there is a clean per-user path, and the first full pass is done at the metadata layer.

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
2. **Full middens battery per user** — mechanically possible by grouping `transcript_path` by `user_id`, materializing each group, and running `middens analyze --all` per group. This should be a batch job with a durable HF token/secrets strategy, because it downloads gated raw transcripts and runs 23 techniques up to ~190 times. Tiny little footgun, that.

## Privacy posture

The SWE-chat README says user prompts and assistant text responses were redacted with Microsoft Presidio and TruffleHog. Good! Still not a blank cheque: the dataset also includes thinking traces, tool results, code changes, repository metadata, and commit tables. The metadata-only pass avoids raw transcript text entirely and hashes `user_id`, `repo_id`, and `owner_id` before writing output.

Raw gated downloads/caches from smoke tests were deleted after use. The local analysis artifacts are under gitignored `experiments/swe-chat-per-user/`.

## Implementation

Script:

```bash
HF_TOKEN=... python3 scripts/analyze_swe_chat_per_user.py --force
```

Outputs:

- `experiments/swe-chat-per-user/summary.json`
- `experiments/swe-chat-per-user/per_user.json`
- `experiments/swe-chat-per-user/per_user_summary.csv`
- `experiments/swe-chat-per-user/report.md`

The script downloads only:

- `sessions.parquet`
- `repositories.parquet`

It writes no raw prompts, assistant text, tool results, diffs, transcript paths, or unhashed user/repo/owner IDs.

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

## How to run the full middens battery per user later

Mechanically:

1. Read `sessions.parquet`.
2. Group by `user_id`, with an explicit `missing_user` group.
3. For each group, download/copy each `transcript_path` into a temporary corpus directory.
4. Run:

   ```bash
   middens analyze <user-corpus-dir> --all --timeout 1800 --force
   middens analyze <user-corpus-dir> --split --no-python
   ```

5. Store only derived manifests/tables/reports, not raw transcripts.
6. Keep raw materialization under `.tmp/` and clean it after each user or shard.

Practical concerns before doing this for all users:

- 190 user groups means up to 190 full Python-technique batteries. That is slow and easy to rate-limit.
- Some user groups have 1–2 sessions; many Python techniques will only emit insufficient-data summaries. A minimum-session threshold may be justified for expensive technique runs, as long as the excluded tail is reported.
- The largest group is `missing_user` with 1,943 sessions. Treat it as its own stratum, not as one real user.
- Trusted CI needs a secret strategy for gated HF access. Do not run this in fork PR contexts.

## Current status

- Metadata-only full per-user analysis: **done**.
- Three-transcript gated parser smoke: **done** (`middens analyze --split --no-python`, all 3 parsed as subagent).
- Full 23-technique per-user battery: **not run yet**; needs batch orchestration and secrets policy.
