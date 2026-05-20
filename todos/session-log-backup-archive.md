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

## Do not implement immediately

This touches raw private transcripts. Start with an NLSpec and follow the repo's adversarial process:

1. Draft NLSpec.
2. Review/deepen it.
3. Red team writes tests from Done criteria only.
4. Green team implements from How only.
5. Keep the orchestrator out of direct test/implementation fixes; route filtered feedback to the right side.

Suggested NLSpec path:

```text
docs/nlspecs/2026-05-20-001-middens-session-archive.md
```

Suggested NLSpec sections:

- Why
- What
- How
- Done
- Non-goals
- Privacy / Safety
- Open questions

## Initial shape

Likely CLI surface:

```bash
middens archive                      # discover known local session stores and copy new logs
middens archive --source claude-code  # restrict to one source tool
middens archive --source codex
middens archive --to ~/agent-session-archive
middens archive --dry-run
middens archive --manifest-only
```

Core behavior:

- Discover known local agent session stores.
- Copy raw session log files into a user-controlled archive directory.
- Never mutate, delete, truncate, or rewrite source logs.
- Deduplicate by content hash.
- Write/update an archive manifest.
- Support dry-run with exact planned actions.
- Fail loudly on ambiguity, unreadable paths, corrupt manifests, and destination collisions.

Archive layout should be deterministic and collision-resistant, probably content-addressed:

```text
archive-root/
  manifest.json
  by-tool/
    claude-code/
      yyyy/mm/<sha256-short>-<basename>.jsonl
    codex/
    pi-coding-agent/
    openclaw/
  indexes/
    sessions.jsonl
    # maybe sessions.parquet later
```

## Manifest fields

Require these per archived file:

- source tool
- original path
- original basename
- archive path
- sha256
- size bytes
- source mtime
- archived_at
- parser status
- session id if parseable
- first timestamp if parseable
- last timestamp if parseable

## Design choices to settle in the NLSpec

### Default archive location

Options:

- Require `--to` for v1 to avoid surprising users by copying raw private transcripts somewhere implicit.
- Or use an XDG-ish default:
  - macOS: `~/Library/Application Support/middens/archive`
  - Linux: `$XDG_DATA_HOME/middens/archive`

Recommendation: require `--to` for the first version unless the NLSpec makes a very explicit privacy confirmation flow.

### Default discovery

Known / likely locations to verify before committing the spec:

- Claude Code: `~/.claude/projects/`
- Codex: confirm from local reality/docs before encoding
- Pi coding-agent: confirm from local reality/docs before encoding
- OpenClaw: confirm from local reality/docs before encoding

Do not guess unknown source locations. If a source is ambiguous, fail clearly with a concrete example of correct input.

### Privacy UX

- Command should print a clear warning that it stores raw transcripts.
- Consider requiring `--yes` for non-dry-run operation.
- `--dry-run` should never require confirmation.
- Ensure likely local archive dirs are gitignored if they can appear inside the repo.

### Collision behavior

- Same hash: dedupe; record additional source path if needed.
- Same destination path but different hash: hard error.
- Same source path but changed content: record as a new archive entry, do not overwrite silently.

### Manifest update semantics

- Atomic write via temp file + rename.
- If manifest is corrupt: fail clearly, do not repair silently.
- If archive file is missing but manifest says present: fail or report drift explicitly. Decide in NLSpec.

### Parser coupling

- Archive should not require parsing to succeed.
- Parseable files get metadata enrichment.
- Unparseable files can still be archived with `parser_status = failed`.
- Consider optional `--require-parseable` strict mode, but do not make it the default.

### Symlinks

Decide explicitly:

- follow source symlinks and archive target file bytes, or
- archive the symlink itself.

Recommendation: follow file symlinks, record both original and canonical path, and reject symlink loops.

### Incremental behavior

- Running twice should be idempotent.
- Second run should report `0 copied, N already archived`.

## First-pass Done criteria

The NLSpec should include testable criteria at least this strict:

- Dry-run discovers fixture files and writes nothing.
- Archive run copies files into deterministic locations.
- Re-running archive is idempotent.
- Same-content duplicate is deduped.
- Different-content destination collision fails clearly.
- Source files are byte-for-byte unchanged.
- Manifest is atomically written and contains required fields.
- Unparseable files are archived with failed parser status.
- Corrupt existing manifest fails clearly.
- `--source` limits discovery.
- Missing/unreadable source path fails clearly with an example fix.
- Privacy warning is visible on non-dry-run.

## Code areas to inspect before drafting the NLSpec

Likely relevant areas:

```text
middens/src/corpus/
middens/src/parser/
middens/src/storage/
middens/src/commands/
middens/src/main.rs
```

Look specifically for:

- corpus discovery
- parser autodetection
- manifest/fingerprint utilities
- XDG path handling
- atomic write patterns

## Recommended first concrete action

Draft the NLSpec only, then pause for review. Do not start implementation in the same breath; this is raw private data plumbing, so two beats of paranoia are not excessive.
