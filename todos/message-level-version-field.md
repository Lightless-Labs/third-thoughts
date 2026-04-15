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

Two complementary changes:

**Message level** — for cross-session corpus slices:
- Add `version: Option<String>` to `Message` in `src/session.rs`
- In the Claude Code parser (`src/parser/claude_code.rs`), populate `message.version` from `entry.version` for each parsed turn

**Session level** — for cheap session-level queries:
- Replace `SessionMetadata::version: Option<String>` with `SessionMetadata::versions: Vec<String>` (insertion-ordered, deduped — i.e. append each new version seen as it first appears)
- Lets you answer "did this session span a release?" without scanning every message
- A session with `versions.len() > 1` crossed at least one CLI update boundary

## Impact on techniques

- Per-turn version filtering: use `message.version`
- Session-level version filtering: use `session.metadata.versions`
- The compound scoping rule gains a fifth axis: `cli_version ∈ {range or exact}`
- Do not use `session.metadata.versions[0]` as a proxy for "the session's version" — that's the old mistake restated

## Notes

- The `version` field is present on every line of the raw JSONL (not just the preamble) — confirmed across corpus spanning 2.1.36–2.1.92
- ~25 distinct versions in the current corpus
- This is a schema change; Parquet output column set will gain a `version` field per message row
