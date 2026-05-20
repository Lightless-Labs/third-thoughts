---
title: "Backup and archive local agent session logs before vendor retention deletes them"
status: todo
priority: P0
tags: [corpus, backup, retention, distribution]
source: user-direction-2026-05-20
---

## Why

Claude Code clears local/remote session history after roughly a month. Codex and other agent tools may have similar retention behavior now or later. `middens` depends on raw session logs; if we do not archive them early, the corpus quietly rots. Very scholarly. Very avoidable.

## What

Add a safe, boring session archival path for supported agent logs:

- Claude Code session logs
- Codex session logs
- Pi coding-agent sessions
- OpenClaw sessions
- future parser-backed tools as they appear

The feature should copy raw logs into a user-controlled archive location without mutating the source logs. It should preserve enough metadata to reproduce analyses and detect duplicate/backfilled sessions.

## Initial shape

Likely CLI surface:

```bash
middens archive                     # discover known local session stores and copy new logs
middens archive --source claude-code # restrict to one source tool
middens archive --to ~/agent-session-archive
middens archive --dry-run
middens archive --manifest-only
```

Archive layout should be deterministic and collision-resistant, probably content-addressed:

```text
archive-root/
  manifest.json
  by-tool/
    claude-code/
      yyyy/mm/<hash>-<basename>.jsonl
    codex/
    pi-coding-agent/
  indexes/
    sessions.parquet or sessions.jsonl
```

## Requirements / guardrails

- Never delete or rewrite source logs.
- Never silently overwrite different content at the same destination path.
- Deduplicate by content hash and source metadata.
- Record archive manifest fields: source tool, original path, basename, size, sha256, mtime, archive path, first/last timestamp when parseable, parser status.
- Support dry-run with counts and planned copy actions.
- Make privacy risk explicit: this backs up raw transcripts and should not be committed.
- Fail clearly if a default source location is ambiguous or unreadable.
- Prefer local filesystem first; remote/object storage can be later.

## Process note

This is non-trivial and touches private raw data. Before implementation, write an NLSpec and run the adversarial red/green process. The Done criteria should be strict about no source mutation, deduplication, dry-run behavior, and clear error handling.
