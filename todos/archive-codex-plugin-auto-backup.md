---
title: "Codex plugin/hook for automatic middens session archives"
status: done
priority: P1
tags: [archive, retention, codex, plugin, hooks, automation, privacy]
source: user-direction-2026-05-21
---

## Why

Codex CLI sessions are part of the supported `middens` corpus. If Codex local retention changes or users clean state directories, those logs disappear just as quietly as Claude Code logs. The archive command supports `--source codex`; the next improvement is an opt-in automation layer.

## What

Investigate and, if supported, build a self-contained Codex CLI plugin/hook that regularly archives Codex session logs without requiring a separately installed `middens` CLI.

The plugin should write a `middens archive`-compatible content-addressed archive shape, but package its own archival logic so the retention integration does not depend on a second install step.

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
- Package archival logic with the plugin; do not require `middens` to be installed on `PATH`.
- Write the same core archive structure: content-addressed objects, `manifest.json`, and `indexes/sessions.jsonl`.
- Avoid overlapping runs; rely on the bundled archiver lock as the final guard, but do not intentionally spam it.
- Surface errors without raw transcript content.
- If implemented as a wrapper/scheduler rather than a plugin, document that honestly. No pretending a cron job is a plugin wearing a nice hat.

## Done

**Completed:** 2026-05-21 — Codex plugin implemented at `integrations/codex/middens-archive/`, with a local marketplace at `integrations/codex/.agents/plugins/marketplace.json`. Research result: Codex supports plugins, local marketplaces, skills, and lifecycle hooks gated by the `plugin_hooks` feature; plugin hooks expose `PLUGIN_ROOT`.

- [x] Codex plugin/hook capabilities are researched and documented.
- [x] If a suitable API exists, an integration is implemented under a clear path such as `integrations/codex/middens-archive/`.
- [x] If no suitable API exists, an explicit fallback automation is provided and documented.
- [x] Archive destination is explicit and required.
- [x] The integration packages a bundled archiver for `codex` and does not require the `middens` CLI.
- [x] Repeated invocations are debounced or otherwise bounded.
- [x] Failures are visible and do not leak raw transcript content.
- [x] README documents install, config, privacy warning, uninstall, and manual fixture testing.
- [x] Tests use fixture `HOME` / fixture `.codex/sessions`, never private real sessions.

## Cross-references

- `docs/nlspecs/2026-05-20-001-middens-session-archive.md`
- `todos/archive-pi-extension-auto-backup.md`
- `todos/archive-claude-code-plugin-auto-backup.md`
