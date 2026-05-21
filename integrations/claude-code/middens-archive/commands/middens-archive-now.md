---
description: Archive Claude Code session logs now with the bundled middens archiver
allowed-tools: [Bash]
---

Run the bundled middens archiver for Claude Code session logs now.

Require `MIDDENS_ARCHIVE_ROOT` to be set. Do not accept or invent a default path.

Use this exact shell pattern:

```bash
ARCHIVE_ROOT="${MIDDENS_ARCHIVE_ROOT:-}"
if [ -z "$ARCHIVE_ROOT" ]; then
  echo "MIDDENS_ARCHIVE_ROOT is unset. Set it before running the archive."
  exit 2
fi
node "${CLAUDE_PLUGIN_ROOT}/scripts/archive.mjs" --source claude-code --to "$ARCHIVE_ROOT"
```

Do not print transcript contents.
