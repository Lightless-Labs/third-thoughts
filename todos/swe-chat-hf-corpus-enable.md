---
title: "Enable SALT-NLP/SWE-chat as a gated HF analysis corpus"
status: todo
priority: P1
tags: [huggingface, swe-chat, gated-dataset, public-corpus, ci]
source: user-shared-hf-dataset-2026-05-26
---

## Why

`SALT-NLP/SWE-chat` looks like a very strong public corpus for middens regression and research runs: real-world coding-agent sessions, 5.8k-ish raw transcript JSONL files, and companion Parquet tables for sessions, repositories, checkpoints, commits, and conversations.

It is also gated. Unauthenticated transcript download at pinned revision `f66cca95b14caaa4177f7ed5eaa424608dadcffa` fails with HTTP 401 / `GatedRepoError`, so it cannot be added to normal public PR CI yet.

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

## Done

- [ ] Access/token available for dataset download in trusted CI contexts.
- [ ] Materialization succeeds without raw snippets committed.
- [ ] Parser or normalizer support is validated.
- [ ] PII-redaction scope is documented for fields middens consumes/emits.
- [ ] Registry entry is `analysis_enabled=true` with an explicit CI tier.
- [ ] Full 23-technique analysis completes.
- [ ] Split smoke validates `interactive`, `subagent`, and `autonomous` strata.
- [ ] Methodology docs record the gated-access caveat.
