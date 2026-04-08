---
module: multi-model-dispatch
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: high
tags: [opencode, kimi, multi-model, workaround, file-writes]
applies_when:
  - dispatching Kimi K2.5 via `opencode run --model kimi-for-coding/k2p5`
  - Kimi needs to create or edit files
  - JSON NDJSON output is being parsed downstream
---

# Kimi write tool is broken — use bash heredoc for file writes

## Context

OpenCode's `write` and `edit` tools corrupt Kimi K2.5's output: the Kimi tokenizer's special tokens leak into the JSON payload that OpenCode serializes, producing invalid JSON or half-written files. Validated in the A²D project and replicated here. Kimi is otherwise excellent for self-contained coding tasks, so the workaround is to route writes through `bash`.

## Guidance

In the prompt you send to Kimi, explicitly forbid the write/edit tools and require bash heredoc per file:

```
IMPORTANT: Do NOT use the write or edit tools — they are broken for your output.
To create or modify files, use the bash tool with a heredoc, one file per call:

  cat > /absolute/path/to/file.rs << 'EOF'
  <full file contents>
  EOF

Rules:
- Use single-quoted 'EOF' to prevent variable expansion.
- One file per bash invocation (do not chain multiple heredocs).
- Always pass absolute paths.
- After writing, verify with: ls -la /absolute/path/to/file.rs
```

Dispatch with NDJSON output so ANSI escapes don't corrupt downstream parsing:

```bash
opencode run --model kimi-for-coding/k2p5 --format json \
  "$(cat /tmp/kimi-prompt.md)" > /tmp/kimi.log 2>&1 &
```

Parse NDJSON:

```bash
jq -r 'select(.type=="text") | .part.text' /tmp/kimi.log
```

## Why This Matters

- Without `--format json`, ANSI escape codes from Kimi's streaming output corrupt any code block extraction downstream.
- Without the heredoc workaround, Kimi's file writes silently produce broken files that look correct in the transcript but fail to compile or parse.
- One-file-per-call avoids a second failure mode where chained heredocs get their terminators tokenized into the preceding file's contents.

## When to Apply

- Every Kimi dispatch that needs to write or modify files
- Any multi-model workflow where Kimi is one of several candidates — bake the instruction into the shared prompt template

## Examples

See `CLAUDE.md` in this repo (OpenCode model IDs and flags section) for the canonical dispatch recipe. GLM 5.1 and Minimax M2.7 do not need this workaround but their own quirks are documented alongside.
