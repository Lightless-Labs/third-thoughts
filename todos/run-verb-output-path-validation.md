---
title: "middens run: validate -o output path early"
status: todo
priority: P3
issue_id: null
tags: [cli, run-verb, validation]
source: coderabbit-review-2026-04-14
---

## Problem

`middens run -o <path>` currently fails late (during export) if the output path is invalid. Three cases should be caught early, before running the analyze and interpret steps:

1. Parent directory does not exist
2. Path is not writable (permissions)
3. Path is an existing directory rather than a file

## Proposal

Add a preflight check at the top of the `Commands::Run` match arm (after flag validation, before `→ analyzing...`). If `output` is `Some(path)`:

1. If `path` is an existing directory → bail with "output path is a directory, expected a file path: `<path>`"
2. If parent directory doesn't exist → bail with "output directory does not exist: `<parent>`; create it first"
3. Skip permissions check for now (complex cross-platform, low value vs. the above two).

Update `docs/nlspecs/run-verb-nlspec.md` DoD to document this behavior.
