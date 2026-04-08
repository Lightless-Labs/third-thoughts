---
module: multi-model-dispatch
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [opencode, gemini-cli, codex-cli, multi-model, timeouts, dispatch]
applies_when:
  - dispatching work to Codex, Gemini, or OpenCode CLIs from an orchestrator
  - running adversarial red/green workflows
  - a CLI is being used in background mode
---

# OpenCode / Gemini / Codex CLI dispatch gotchas

## Context

The third-thoughts adversarial workflow routes red-team and green-team work to external CLIs to enforce context isolation. Each CLI has non-obvious flags whose defaults will bite you once and waste 10+ minutes of compute each time.

## Guidance

### Codex CLI

```bash
codex exec --skip-git-repo-check --full-auto -o /tmp/codex-out.md "<prompt>"
```

- **Always** set `timeout: 600000` (10 min) on the Bash tool call. Default 120s auto-backgrounds Codex and you lose the output silently.
- **Always** use `-o <file>` instead of piping. Piped stdout doesn't flush on background, and a 10-minute run will produce an empty file.
- `--full-auto` skips interactive confirmations. `--skip-git-repo-check` lets Codex run outside the target repo's git root (useful when dispatching from a parent monorepo).

### Gemini CLI

```bash
gemini -y -s false --prompt "<prompt>"
```

- `-y` is yolo mode (skip confirmations)
- `-s false` disables sandbox — required for Gemini to write files. Default sandbox mode silently drops writes.
- No `-o` flag; capture stdout to a file yourself. Gemini flushes reliably so piping is fine.

### OpenCode CLI

```bash
opencode run --model <provider/model> --format json "<prompt>" > /tmp/oc.log 2>&1 &
```

- Dispatch in background — runs can take 5-15 minutes for GLM 5.1 and Minimax M2.7.
- `--format json` produces NDJSON; without it ANSI escapes corrupt downstream code extraction.
- **Model IDs are strict.** `kimi-for-coding/k2p5` works; `kimi/kimi-k2.5` fails silently (empty output, no error).
- Parse NDJSON with `jq -r 'select(.type=="text") | .part.text' /tmp/oc.log`.

## Why This Matters

- Every one of these defaults has burned at least one 10-minute compute run in this project's history. Document once, stop paying the cost.
- Silent failures (empty output, truncated files, "no such model") are the worst kind — they look like the model "didn't do anything" and trigger pointless retries.
- Background dispatch + NDJSON parsing lets an orchestrator fan out red/green tasks across 3+ CLIs in parallel without blocking.

## When to Apply

- Every dispatch. There are no exceptions where the default flags are correct.
- Bake these invocations into a shared script or skill (`/codex-cli`, `/gemini-cli`, `/opencode-cli`) so orchestrators don't re-derive them.

## Examples

Parallel red-team dispatch to three CLIs from a single Bash call:

```bash
codex exec --skip-git-repo-check --full-auto -o /tmp/codex.md "$(cat /tmp/red-prompt.md)" &
gemini -y -s false --prompt "$(cat /tmp/red-prompt.md)" > /tmp/gemini.md &
opencode run --model kimi-for-coding/k2p5 --format json "$(cat /tmp/red-prompt.md)" > /tmp/kimi.log 2>&1 &
wait
```

All three run concurrently, outputs land in deterministic files, timeout on the Bash call is `600000`.

See `CLAUDE.md` "Multi-Model Analysis" section for the canonical reference.
