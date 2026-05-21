---
title: "Review self-contained archive plugins with Codex 5.5 xhigh via Pi"
status: done
priority: P0
tags: [archive, plugins, review, codex, pi, privacy, retention]
source: user-direction-2026-05-21
---

## Why

The Pi, Claude Code, and Codex archive integrations now copy raw agent transcripts into a user-selected archive without relying on an installed `middens` CLI. That is exactly the kind of thing that deserves a second pair of eyes before we pat ourselves on the back and accidentally archive a footgun with a bow on it.

The next session's top priority is to have all three reviewed by **Codex 5.5 xhigh using Pi**.

## Scope

Review these integration packages together:

- `integrations/pi/middens-archive/`
- `integrations/claude-code/middens-archive/`
- `integrations/codex/middens-archive/`
- Shared/bundled archiver copies at each `scripts/archive.mjs`
- Marketplace/package manifests:
  - `package.json`
  - `integrations/claude-code/.claude-plugin/marketplace.json`
  - `integrations/codex/.agents/plugins/marketplace.json`

## Review focus

Ask Codex 5.5 xhigh to review for:

- Privacy failures: transcript contents in logs, notifications, command output, errors, manifests beyond intended paths.
- Archive safety: source/archive overlap checks, lock behavior, atomic writes, drift validation, destination collision handling.
- Self-contained packaging: no accidental dependency on `middens` being installed on `PATH`.
- Agent-specific correctness: Pi extension API usage, Claude Code hooks/commands, Codex marketplace/hooks/skills.
- Misleading docs: install paths, env vars, dry-run behavior, uninstall notes.
- Test gaps: fixture coverage, malformed JSONL behavior, empty sessions, duplicate observations, debounce/lock edge cases.
- Compatibility risk: whether the bundled JS archive format stays close enough to `middens archive` for downstream consumers.

## Suggested Pi Dispatch

First confirm the exact Codex 5.5 xhigh model identifier available to Pi:

```bash
pi --list-models codex
```

Then run a non-interactive review via Pi using the Codex 5.5 xhigh model. Adjust the model string if Pi reports a different ID:

```bash
pi -p \
  --model codex/codex-5.5:xhigh \
  --append-system-prompt "You are performing a privacy/security/code review. Prioritize concrete defects over style." \
  "Review the self-contained archive plugins in integrations/pi/middens-archive, integrations/claude-code/middens-archive, and integrations/codex/middens-archive. Focus on privacy, raw transcript handling, archive safety, plugin API correctness, install docs, and tests. Return findings ordered by severity with file paths and actionable fixes."
```

If Pi's CLI/model syntax has changed, use the current Pi help/list-models output rather than guessing.

## Done

- [x] Codex 5.5 xhigh review is run through Pi, not directly through Codex CLI.
- [x] Review output is saved under `docs/reviews/` with a date-stamped filename.
- [x] Findings are triaged into P0/P1/P2 buckets.
- [x] Any confirmed P0/P1 issues are fixed or filed as dedicated todos.
- [x] The three plugin todos remain done unless the review finds a release-blocking issue that requires reopening them.
- [x] `docs/HANDOFF.md` is updated with the review result and next action.

## Cross-references

- `todos/archive-pi-extension-auto-backup.md`
- `todos/archive-claude-code-plugin-auto-backup.md`
- `todos/archive-codex-plugin-auto-backup.md`
- `docs/HANDOFF.md`
