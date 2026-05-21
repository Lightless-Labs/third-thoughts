#!/usr/bin/env node
import { archiveSessions } from "../scripts/archive.mjs";

try {
  const result = await archiveSessions({
    source: "claude-code",
    archiveRoot: process.env.MIDDENS_ARCHIVE_ROOT,
    quiet: true,
    debounce: process.argv[2] !== "stop",
  });

  console.log(JSON.stringify({}));
  process.exit(0);
} catch (error) {
  const message = error instanceof Error ? error.message.split(/\r?\n/, 1)[0] : "archive failed";
  console.log(JSON.stringify({ systemMessage: `middens archive failed: ${message}` }));
  process.exit(0);
}
