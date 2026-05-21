---
title: "Pi extension for automatic middens session archives"
status: done
priority: P1
tags: [archive, retention, pi, extension, automation, privacy]
source: user-direction-2026-05-21
---

## Why

`middens archive` now exists, but humans forget to run boring backup commands. Pi has a real TypeScript extension API with lifecycle/session events, commands, UI notifications, and `pi.exec`, so a Pi-side auto-archive integration is feasible and should be the first automation target.

This still touches raw transcripts, so the extension must be explicit, quiet, and hard to accidentally misconfigure. The goal is "regularly copy logs into the archive the user chose", not "spray private conversations into a surprise directory". Tiny but important distinction.

## What

Build a Pi extension / pi package that periodically invokes:

```bash
middens archive --source pi-coding-agent --to <archive-root> --yes
```

and exposes a manual command such as:

```text
/middens-archive-now
/middens-archive-status
```

Suggested package shape:

```text
integrations/pi/middens-archive/
  package.json
  extensions/
    middens-archive.ts
  README.md
```

Pi docs read before filing this todo:

- `/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md`
- `/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/docs/packages.md`
- `/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/README.md`
- Relevant examples: `file-trigger.ts`, `shutdown-command.ts`, `auto-commit-on-exit.ts`

## Initial design

Configuration should be explicit, probably via env vars first:

```bash
export MIDDENS_ARCHIVE_ROOT="$HOME/agent-session-archive"
export MIDDENS_ARCHIVE_INTERVAL_MINUTES=60
```

Optional later config via extension command/UI is fine, but v1 should not require writing a settings subsystem.

Trigger candidates:

- `session_start`: schedule a debounced interval timer.
- `session_shutdown`: run one final archive if enough time has elapsed.
- `/middens-archive-now`: user-triggered immediate archive.

Use `pi.exec` or Node `child_process` to run `middens`. Prefer `pi.exec` when possible because it fits Pi cancellation/observability patterns.

## Safety requirements

- If `MIDDENS_ARCHIVE_ROOT` is unset, do nothing except optionally show one non-spammy warning/status.
- Never invent a default archive path.
- Do not run more frequently than the configured interval; guard against overlapping runs.
- Use `middens archive`'s lock file and also keep an in-extension `running` flag.
- Surface failures with `ctx.ui.notify(..., "error")` when UI exists; log otherwise.
- Do not include raw transcript content in notifications, logs, or tool results.
- Package README must warn that archive roots contain raw transcripts and should stay private/out of git.

## Done

**Completed:** 2026-05-21 — implemented as `integrations/pi/middens-archive/`, with a bundled self-contained archiver, local package install, and temp-`HOME` smoke tests. Updated the same day to stop requiring a separately installed `middens` CLI.

- [x] A Pi extension package exists under `integrations/pi/middens-archive/` or another documented path.
- [x] It can be loaded with `pi -e <path>` for local testing.
- [x] It can be installed as a Pi package from a local path or git URL.
- [x] With `MIDDENS_ARCHIVE_ROOT` unset, it performs no archive writes.
- [x] With `MIDDENS_ARCHIVE_ROOT` set, `/middens-archive-now` invokes the bundled archiver for `pi-coding-agent` and writes a `middens archive`-compatible archive.
- [x] Periodic scheduling is debounced and does not start overlapping archive runs.
- [x] Shutdown-triggered archive is best-effort and bounded by a timeout.
- [x] Errors are visible but do not leak transcript content.
- [x] README documents install, config, privacy implications, and uninstall.
- [x] Tested against a fixture `$PI_CODING_AGENT_SESSION_DIR` or temp `HOME`, not private real sessions.

## Cross-references

- `docs/nlspecs/2026-05-20-001-middens-session-archive.md`
- `todos/archive-claude-code-plugin-auto-backup.md`
- `todos/archive-codex-plugin-auto-backup.md`
