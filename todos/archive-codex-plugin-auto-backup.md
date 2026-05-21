---
title: "Codex plugin/hook for automatic middens session archives"
status: todo
priority: P1
tags: [archive, retention, codex, plugin, hooks, automation, privacy]
source: user-direction-2026-05-21
---

## Why

Codex CLI sessions are part of the supported `middens` corpus. If Codex local retention changes or users clean state directories, those logs disappear just as quietly as Claude Code logs. The archive command supports `--source codex`; the next improvement is an opt-in automation layer.

## What

Investigate and, if supported, build a Codex CLI plugin/hook that regularly invokes:

```bash
middens archive --source codex --to <archive-root> --yes
```

If Codex has no stable plugin/hook surface, provide a documented fallback: wrapper script, shell alias, LaunchAgent/systemd timer, or another explicit user-installed scheduler.

## Required research first

Do **not** assume Codex has a plugin API. First pass should answer:

- Does Codex CLI support plugins, hooks, lifecycle scripts, or slash commands?
- Can a hook run after a session is saved or on CLI shutdown?
- Is there a stable default session path beyond the current `~/.codex/sessions` convention?
- Can integration tests safely redirect Codex session storage to a fixture path?
- What user-facing install path is least surprising?

Document the research before implementation.

## Initial design constraints

- Archive destination must be explicit (`MIDDENS_ARCHIVE_ROOT` or equivalent config).
- Do not invent a default archive root.
- Prefer calling the CLI:

  ```bash
  middens archive --source codex --to "$MIDDENS_ARCHIVE_ROOT" --yes
  ```

- Avoid overlapping runs; rely on `middens archive` lock as the final guard, but do not intentionally spam it.
- Surface errors without raw transcript content.
- If implemented as a wrapper/scheduler rather than a plugin, document that honestly. No pretending a cron job is a plugin wearing a nice hat.

## Done

- [ ] Codex plugin/hook capabilities are researched and documented.
- [ ] If a suitable API exists, an integration is implemented under a clear path such as `integrations/codex/middens-archive/`.
- [ ] If no suitable API exists, an explicit fallback automation is provided and documented.
- [ ] Archive destination is explicit and required.
- [ ] The integration invokes `middens archive --source codex`; archive logic is not duplicated.
- [ ] Repeated invocations are debounced or otherwise bounded.
- [ ] Failures are visible and do not leak raw transcript content.
- [ ] README documents install, config, privacy warning, uninstall, and manual dry-run.
- [ ] Tests use fixture `HOME` / fixture `.codex/sessions`, never private real sessions.

## Cross-references

- `docs/nlspecs/2026-05-20-001-middens-session-archive.md`
- `todos/archive-pi-extension-auto-backup.md`
- `todos/archive-claude-code-plugin-auto-backup.md`
