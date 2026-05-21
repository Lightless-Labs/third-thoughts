# Codex middens archive plugin

Self-contained Codex plugin that archives raw Codex JSONL sessions into a user-selected content-addressed archive. It does **not** require the `middens` CLI to be installed.

## Privacy warning

The archive root contains raw transcripts: prompts, tool results, paths, and possibly secrets. Keep it private and out of git.

## Configuration

The plugin never chooses a destination for you:

```bash
export MIDDENS_ARCHIVE_ROOT="$HOME/agent-session-archive"
```

Optional:

```bash
# Default: 60. Hooks use this to debounce SessionStart/UserPromptSubmit archives.
export MIDDENS_ARCHIVE_INTERVAL_MINUTES=60
```

## Install / test

Add the local marketplace that contains this plugin:

```bash
codex plugin marketplace add ./integrations/codex
```

Then enable/install `middens-archive` from Codex's plugin UI/flow.

## Hooks and skills

The plugin declares lifecycle hooks for:

- `SessionStart` — debounced archive
- `UserPromptSubmit` — debounced archive
- `Stop` — final best-effort archive

It also ships skills:

- `middens-archive-now`
- `middens-archive-status`

The bundled archiver discovers `~/.codex/sessions` unless `--from` is used when running `scripts/archive.mjs` directly.

## Manual dry run

```bash
node ./integrations/codex/middens-archive/scripts/archive.mjs \
  --source codex \
  --from /path/to/fixture/.codex/sessions \
  --to /path/to/archive \
  --dry-run
```

## Uninstall

Disable/remove the plugin through Codex's plugin manager, then remove the `MIDDENS_ARCHIVE_ROOT` export from your shell profile if you no longer want automatic archives.
