# Claude Code middens archive plugin

Self-contained Claude Code plugin that archives raw Claude Code JSONL sessions into a user-selected content-addressed archive. It does **not** require the `middens` CLI to be installed.

## Privacy warning

The archive root contains raw transcripts: prompts, tool results, file paths, and possibly secrets. Keep it private and out of git.

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

For one Claude Code run:

```bash
claude --plugin-dir ./integrations/claude-code/middens-archive
```

Or add this plugin through your normal Claude Code plugin marketplace flow. The plugin root is `integrations/claude-code/middens-archive`.

## Hooks and command

The plugin installs hooks for:

- `SessionStart` — debounced archive
- `UserPromptSubmit` — debounced archive
- `Stop` — final best-effort archive

Manual command:

```text
/middens-archive-now [archive-root]
```

The bundled archiver discovers `~/.claude/projects` unless `--from` is used when running `scripts/archive.mjs` directly.

## Manual dry run

To inspect what would be archived, point `HOME` at a fixture and run:

```bash
node ./integrations/claude-code/middens-archive/scripts/archive.mjs \
  --source claude-code \
  --from /path/to/fixture/.claude/projects \
  --to /path/to/archive \
  --dry-run
```

## Uninstall

Disable/remove the plugin through Claude Code's plugin manager, then remove the `MIDDENS_ARCHIVE_ROOT` export from your shell profile if you no longer want automatic archives.
