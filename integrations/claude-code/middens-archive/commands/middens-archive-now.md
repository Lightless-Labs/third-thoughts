---
description: Archive Claude Code session logs now with the bundled middens archiver
argument-hint: "[archive-root]"
allowed-tools: [Bash]
---

Run the bundled middens archiver for Claude Code session logs now.

If `$ARGUMENTS` is non-empty, use it as the archive root. Otherwise require `MIDDENS_ARCHIVE_ROOT` to be set. Do not invent a default path.

Use this exact shell pattern:

```bash
ARCHIVE_ROOT="${ARGUMENTS:-${MIDDENS_ARCHIVE_ROOT:-}}"
if [ -z "$ARCHIVE_ROOT" ]; then
  echo "MIDDENS_ARCHIVE_ROOT is unset. Set it or pass an explicit archive root."
  exit 2
fi
node "${CLAUDE_PLUGIN_ROOT}/scripts/archive.mjs" --source claude-code --to "$ARCHIVE_ROOT"
```

Do not print transcript contents.
