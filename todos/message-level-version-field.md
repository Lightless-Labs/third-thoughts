---
title: "Track CLI version at message level for corpus version stratification"
status: todo
priority: P2
issue_id: null
tags: [parser, session, corpus, stratification, cli-version]
source: session-2026-04-15
---

## Problem

`SessionMetadata::version` captures the first CLI version seen in a session and stops. This is wrong for two reasons:

1. A session can span a CLI update — turns written before and after the update carry different versions, but only the first is recorded.
2. Corpus stratification by version (e.g. "all turns on 2.1.81+") is a cross-session slice. A session that spans a release boundary belongs to both sides. Per-session version metadata cannot express this.

## Solution

Move version tracking to the **message level**:

- Add `version: Option<String>` to `Message` in `src/session.rs`
- In the Claude Code parser (`src/parser/claude_code.rs`), populate `message.version` from `entry.version` for each parsed turn
- `SessionMetadata::version` can be kept as a convenience hint (first version seen) or removed — it should not be used for stratification

## Impact on techniques

Techniques that want to stratify by version should filter on `message.version`, not `session.metadata.version`. The compound scoping rule gains a fifth axis: `cli_version ∈ {range or exact}`.

## Notes

- The `version` field is present on every line of the raw JSONL (not just the preamble) — confirmed across corpus spanning 2.1.36–2.1.92
- ~25 distinct versions in the current corpus
- This is a schema change; Parquet output column set will gain a `version` field per message row
