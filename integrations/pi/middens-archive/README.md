# Pi middens archive extension

A tiny Pi package that archives Pi coding-agent session logs with its bundled archiver. It is intentionally boring: you choose the archive root, it copies raw JSONL logs there, and it tries hard not to do anything surprising.

## Privacy warning

The archive root contains raw transcripts. Treat it like private data:

- do not put it inside a git repository;
- do not sync it to a shared folder unless that is deliberate;
- do not paste archive output into bug reports without checking it first.

`middens archive` writes a git-worktree `.gitignore` guard in the archive root, but that is a seatbelt, not a plan.

## Requirements

- Pi coding-agent with TypeScript extension support.

The package is self-contained and does not require the `middens` CLI to be installed.

## Configuration

The extension never invents a default destination. Set the archive root explicitly:

```bash
export MIDDENS_ARCHIVE_ROOT="$HOME/agent-session-archive"
```

Optional settings:

```bash
# Default: 60. Minimum: 1.
export MIDDENS_ARCHIVE_INTERVAL_MINUTES=60

# Default: 300000 (5 minutes). Minimum: 1000.
export MIDDENS_ARCHIVE_TIMEOUT_MS=300000

# Default: 20000 (20 seconds). Minimum: 1000.
export MIDDENS_ARCHIVE_SHUTDOWN_TIMEOUT_MS=20000
```

With `MIDDENS_ARCHIVE_ROOT` unset, the extension performs no archive writes and shows a single warning/status message.

## Local testing with `pi -e`

From the repository root:

```bash
pi -e ./integrations/pi/middens-archive
```

For a quick command smoke test without touching real sessions, point `HOME` at a temp fixture because the bundled archiver discovers `~/.pi/agent/sessions`:

```bash
tmp_home=$(mktemp -d)
archive_root=$(mktemp -d)
mkdir -p "$tmp_home/.pi/agent/sessions/example"
printf '{"type":"session","id":"fixture"}\n' > "$tmp_home/.pi/agent/sessions/example/session.jsonl"

HOME="$tmp_home" \
MIDDENS_ARCHIVE_ROOT="$archive_root" \
pi --no-extensions --offline --no-session \
  -e ./integrations/pi/middens-archive \
  -p /middens-archive-now

find "$archive_root" -maxdepth 3 -type f | sort
```

The exact fixture JSONL only needs to be valid JSONL for parser metadata to be marked `parsed`; the archive still copies raw logs and records parser status.

Manual dry-run of the bundled archiver:

```bash
node ./integrations/pi/middens-archive/scripts/archive.mjs \
  --source pi-coding-agent \
  --from /path/to/fixture/.pi/agent/sessions \
  --to /path/to/archive \
  --dry-run
```

Regression tests for the shared bundled archiver copies:

```bash
cd integrations/pi/middens-archive && npm test
```

The test suite verifies the Pi, Claude Code, and Codex `scripts/archive.mjs` copies are identical before exercising the shared safety cases.

## Install as a Pi package

Install globally from a local checkout:

```bash
pi install ./integrations/pi/middens-archive
```

Or install for the current project only:

```bash
pi install -l ./integrations/pi/middens-archive
```

A git URL works too because the repository root has a small Pi package manifest that points at this extension:

```bash
pi install git:github.com/Lightless-Labs/third-thoughts
```

For local development, prefer the subdirectory path so you only load this package while poking at it.

## Commands

Inside Pi:

```text
/middens-archive-now
/middens-archive-status
```

`/middens-archive-now` runs immediately, guarded against overlapping runs. The extension also starts an automatic archive when a session begins, then repeats on the configured interval. On session shutdown, the extension performs a best-effort final archive regardless of the debounce interval; that run is bounded by `MIDDENS_ARCHIVE_SHUTDOWN_TIMEOUT_MS`.

## What gets executed

The extension invokes its bundled `scripts/archive.mjs` with:

```bash
node scripts/archive.mjs --source pi-coding-agent --to "$MIDDENS_ARCHIVE_ROOT" --quiet
```

It does not require a separately installed `middens` binary. The bundled archiver performs content-addressing, manifest/index writes, source/archive overlap rejection, destination collision checks, and lock-file protection. The extension also keeps an in-process `running` flag so it does not intentionally start overlapping runs. Belt, suspenders, faint air of paranoia.

## Uninstall

If installed globally:

```bash
pi remove ./integrations/pi/middens-archive
```

If installed in project settings:

```bash
pi remove -l ./integrations/pi/middens-archive
```

Remove the environment variables from your shell profile if you no longer want automatic archives.
