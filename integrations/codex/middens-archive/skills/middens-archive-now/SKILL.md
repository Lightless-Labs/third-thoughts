---
name: middens-archive-now
description: Archive Codex session logs now with the bundled middens archiver
---

Run the bundled middens archiver for Codex session logs now.

If the user supplies an archive root, use that. Otherwise require `MIDDENS_ARCHIVE_ROOT` to be set. Do not invent a default path.

Use this shell pattern from the plugin root:

```bash
ARCHIVE_ROOT="${MIDDENS_ARCHIVE_ROOT:-}"
if [ -z "$ARCHIVE_ROOT" ]; then
  echo "MIDDENS_ARCHIVE_ROOT is unset. Set it before running the archive."
  exit 2
fi
node "${PLUGIN_ROOT}/scripts/archive.mjs" --source codex --to "$ARCHIVE_ROOT"
```

Do not print transcript contents.
