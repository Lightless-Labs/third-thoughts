---
title: "Enable SALT-NLP/SWE-chat as a gated HF analysis corpus"
status: todo
priority: P1
tags: [huggingface, swe-chat, gated-dataset, public-corpus, ci]
source: user-shared-hf-dataset-2026-05-26
---

## Why

`SALT-NLP/SWE-chat` looks like a very strong public corpus for middens regression and research runs: real-world coding-agent sessions, 5.8k-ish raw transcript JSONL files, and companion Parquet tables for sessions, repositories, checkpoints, commits, and conversations.

It is also gated. Unauthenticated transcript download at pinned revision `f66cca95b14caaa4177f7ed5eaa424608dadcffa` fails with HTTP 401 / `GatedRepoError`, so it cannot be added to normal public PR CI yet. A one-off user-provided token smoke on 2026-05-26 confirmed gated access works, three transcript JSONL files download, and current middens parses/analyzes them with `--split --no-python`; the temporary raw/cache/output artifacts were deleted after the smoke.

The README's privacy note is promising: user prompts and assistant text responses were redacted with Microsoft Presidio for named entities and TruffleHog for secrets. Treat that as useful provenance, not blanket clearance: the dataset also advertises thinking traces, tool results, code changes, repository metadata, and commits, so we should still schema-audit what fields land in middens outputs before calling derived artifacts privacy-safe.

## What

Promote `docs/corpora/public-hf-analysis-corpora.json` entry `salt-nlp-swe-chat` from disabled candidate to analysis-enabled corpus once access and format validation are sorted.

## How

1. Accept/request dataset access for the CI HF account/token.
2. Add `HF_TOKEN` as a repo secret if not already present.
3. Wire `HF_TOKEN` through `.github/workflows/hf-corpus-analysis.yml` for non-PR contexts only, or keep this corpus out of PR tiers so fork PRs do not fail without secrets.
4. Smoke materialize a small transcript subset without committing raw data.
5. Verify the transcript JSONL format is accepted by existing parsers, or add a schema-aware normalizer if needed.
6. Audit which transcript fields are redacted. README guarantees user prompts and assistant text responses, but not necessarily thinking/tool-result/code-diff fields.
7. Enable the registry entry with an appropriate tier, probably `full` only at first.
7. Run `middens analyze --all` and `middens analyze --split --no-python` on it.

## Progress notes

- 2026-05-26: Metadata-only full per-user aggregate analysis completed with `scripts/analyze_swe_chat_per_user.py`. Outputs are gitignored under `experiments/swe-chat-per-user/`; sanitized method note is `docs/solutions/methodology/swe-chat-per-user-analysis-20260526.md`. Result: 5,851 sessions, 190 user groups, 1,943 sessions with missing `user_id`.
- 2026-05-26: Full middens per-user battery attempted with `scripts/run_swe_chat_per_user_middens.py` for currently supported/likely-supported agents (`Claude Code`, `claude-code`, `Codex`). Result: 175 selected user groups / 5,066 sessions; 165 groups / 4,999 selected sessions completed with 23/23 technique entries and zero technique errors. Ten groups failed: seven no supported parser matched, three storage PII column-name blocklist failures from MCP tool names containing `content`.

## Done

- [ ] Access/token available for dataset download in trusted CI contexts. (One-off local token smoke succeeded; durable CI secret strategy still pending.)
- [x] Materialization smoke succeeds without raw snippets committed.
- [x] Parser support is smoke-validated on three transcript JSONL files (`middens analyze --split --no-python`: 3 parsed, 0 interactive, 3 subagent, 0 autonomous).
- [x] Full per-user middens batch runner exists and mostly completed for currently supported/likely-supported agents.
- [ ] PII-redaction scope is documented for fields middens consumes/emits.
- [ ] Registry entry is `analysis_enabled=true` with an explicit CI tier.
- [ ] Full 23-technique analysis completes.
- [ ] Split smoke validates `interactive`, `subagent`, and `autonomous` strata.
- [ ] Methodology docs record the gated-access caveat.
