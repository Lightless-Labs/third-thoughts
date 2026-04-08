---
module: agent-workflow
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [edit-tool, lint-on-save, rustfmt, race-condition, agent-workflow]
applies_when:
  - the Edit tool returns "file modified since read"
  - the editor or IDE has lint-on-save / format-on-save enabled
  - rustfmt / prettier / black runs between Read and Edit
---

# Handling "file modified since read" from lint-on-save races

## Context

Claude Code's Edit tool requires that the file hasn't changed on disk between the Read and the Edit. When the user has a Rust-analyzer / rustfmt / prettier "format on save" hook, or an IDE that rewrites files on focus change, the agent's Read-then-Edit pair races against the formatter and fails with `file modified since read`.

## Guidance

1. **First recourse** — re-Read the file and retry the Edit. The second Read picks up the formatter's changes and the Edit applies cleanly. This works 90% of the time.
2. **If the formatter keeps re-triggering** (file is getting saved repeatedly by an external process), batch your edits: Read once, then issue multiple Edit calls in the same turn before the formatter can re-run.
3. **If the failure is persistent**, ask the user to disable format-on-save for the session. Do not work around it by switching to `Write` with a full-file rewrite — that clobbers whatever the formatter already fixed and loses whitespace consistency.
4. **Never** bypass with `bash sed`/`awk`. You lose the Edit tool's uniqueness check and risk silent wrong-replacement.

## Why This Matters

- The error is a safety check, not a bug — it exists so the agent doesn't overwrite the user's in-flight changes.
- Re-Read + retry is cheap (one extra tool call) and preserves the invariant.
- Full-file `Write` rewrites lose the line-level diff reviewers rely on for trust.
- Persistent failures are signals of a workflow mismatch the user should know about, not something to silently route around.

## When to Apply

- Any time Edit returns `file modified since read`
- Proactively when working in a repo you know has aggressive formatters (Rust with rust-analyzer, TypeScript with biome, Python with ruff-format on save)

## Examples

Recovery pattern:

```text
Edit(file=foo.rs, old=..., new=...)
  -> Error: file modified since read

Read(file=foo.rs)            # picks up formatter's changes
Edit(file=foo.rs, old=..., new=...)   # retry, succeeds
```

Batched edits to outrun the formatter:

```text
Read(file=foo.rs)
Edit(old=A1, new=B1), Edit(old=A2, new=B2), Edit(old=A3, new=B3)   # all in one turn
```

If still failing, tell the user:

> Your format-on-save is racing with the agent's edits on `foo.rs`. Mind disabling
> it for this file while I finish the refactor? I'll re-enable it in my next commit.
