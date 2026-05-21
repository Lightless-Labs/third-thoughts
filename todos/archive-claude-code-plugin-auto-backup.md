---
title: "Claude Code hook/plugin for automatic middens session archives"
status: done
priority: P1
tags: [archive, retention, claude-code, plugin, hooks, automation, privacy]
source: user-direction-2026-05-21
---

## Why

Claude Code session retention is the original reason `middens archive` exists. A manual command is useful; a small Claude Code integration that backs up sessions regularly would be better, because researchers are still human and humans are cron jobs with feelings.

## What

Investigate and, if supported, build a self-contained Claude Code plugin/hook that periodically archives Claude Code session logs without requiring a separately installed `middens` CLI.

The plugin should still write a `middens archive`-compatible content-addressed archive shape, but package its own archival logic because requiring users to install a second binary for a retention safety net is how tiny footguns become medium footguns.

## Required research first

Do **not** guess the Claude Code extension surface. First pass should answer:

- Does Claude Code currently support first-party plugins, hooks, slash commands, or lifecycle scripts?
- Can any hook run on session start/end or at safe intervals?
- Where should configuration live?
- What is the most conservative way to avoid archiving without explicit user consent?
- Can an integration be distributed in this repo without depending on private Claude internals?

Record the answer in this todo or a small solution doc before implementation.

## Initial design constraints

- No default archive destination. Require an explicit config value, e.g. `MIDDENS_ARCHIVE_ROOT` or a generated config file.
- Package archival logic with the plugin; do not require `middens` to be installed on `PATH`.
- Write the same core archive structure: content-addressed objects, `manifest.json`, and `indexes/sessions.jsonl`.
- Debounce runs and avoid overlap. The bundled archiver should keep a lock file and the integration should still avoid hammering it.
- Include a manual "archive now" path if Claude Code supports commands/hooks; otherwise document the manual command.
- Never print transcript contents.

## Done

**Completed:** 2026-05-21 — Claude Code plugin implemented at `integrations/claude-code/middens-archive/`. Research result: Claude Code supports plugin manifests, marketplaces, commands, and hooks; hook config loads from plugin-local `hooks/hooks.json` and exposes `CLAUDE_PLUGIN_ROOT`.

- [x] Claude Code plugin/hook capabilities are researched and documented.
- [x] If a plugin/hook API exists, an integration is implemented under a clear path such as `integrations/claude-code/middens-archive/`.
- [x] If no suitable API exists, a documented fallback automation is provided instead (LaunchAgent/systemd timer/wrapper), with the limitation clearly stated.
- [x] Archive destination is explicit and required.
- [x] The integration packages a bundled archiver for `claude-code` and does not require the `middens` CLI.
- [x] Repeated invocations are debounced or otherwise bounded.
- [x] Failures are visible and do not leak raw transcript content.
- [x] README documents install, config, privacy warning, uninstall, and manual fixture testing.
- [x] Tests use fixture `HOME` / fixture `.claude/projects`, never private real sessions.

## Cross-references

- `docs/nlspecs/2026-05-20-001-middens-session-archive.md`
- `todos/archive-pi-extension-auto-backup.md`
- `todos/archive-codex-plugin-auto-backup.md`
