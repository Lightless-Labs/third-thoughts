---
title: "Claude Code hook/plugin for automatic middens session archives"
status: todo
priority: P1
tags: [archive, retention, claude-code, plugin, hooks, automation, privacy]
source: user-direction-2026-05-21
---

## Why

Claude Code session retention is the original reason `middens archive` exists. A manual command is useful; a small Claude Code integration that backs up sessions regularly would be better, because researchers are still human and humans are cron jobs with feelings.

## What

Investigate and, if supported, build a Claude Code plugin/hook that periodically invokes:

```bash
middens archive --source claude-code --to <archive-root> --yes
```

If Claude Code does not expose a stable plugin/hook API suitable for this, produce the safest equivalent automation: a documented wrapper, LaunchAgent/systemd timer, or shell hook that users explicitly install.

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
- Prefer calling the already-implemented CLI rather than duplicating archive logic.
- Use only:

  ```bash
  middens archive --source claude-code --to "$MIDDENS_ARCHIVE_ROOT" --yes
  ```

  unless the user configures additional flags.
- Debounce runs and avoid overlap. `middens archive` has its own lock file; the integration should still avoid hammering it.
- Include a manual "archive now" path if Claude Code supports commands/hooks; otherwise document the manual command.
- Never print transcript contents.

## Done

- [ ] Claude Code plugin/hook capabilities are researched and documented.
- [ ] If a plugin/hook API exists, an integration is implemented under a clear path such as `integrations/claude-code/middens-archive/`.
- [ ] If no suitable API exists, a documented fallback automation is provided instead (LaunchAgent/systemd timer/wrapper), with the limitation clearly stated.
- [ ] Archive destination is explicit and required.
- [ ] The integration invokes `middens archive --source claude-code` and does not reimplement raw-copy logic.
- [ ] Repeated invocations are debounced or otherwise bounded.
- [ ] Failures are visible and do not leak raw transcript content.
- [ ] README documents install, config, privacy warning, uninstall, and how to run a dry-run manually.
- [ ] Tests use fixture `HOME` / fixture `.claude/projects`, never private real sessions.

## Cross-references

- `docs/nlspecs/2026-05-20-001-middens-session-archive.md`
- `todos/archive-pi-extension-auto-backup.md`
- `todos/archive-codex-plugin-auto-backup.md`
