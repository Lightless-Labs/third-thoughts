---
title: "Clarify undefined symbols in dynamic timeout formula"
status: todo
priority: P3
issue_id: null
tags: [python-bridge, scaling, cli, techniques, docs]
source: coderabbit-review-2026-04-14
---

## Problem

`todos/python-technique-dynamic-timeout.md` lines 17–19 use `base_seconds` and `f(median_session_bytes)` without defining them:

```
computed = base_seconds × log(session_count) × f(median_session_bytes)
```

The implementation (already done as `clamp(100×ln(n), 60, 1800)`) does NOT use `median_session_bytes` at all — it simplified to session count only. The todo doc is therefore stale and misleading.

## Action

Update `todos/python-technique-dynamic-timeout.md` Design section to reflect the actual implemented formula: `clamp(100 × ln(session_count), 60, 1800)`. Mark the `median_session_bytes` factor as deferred/dropped (the corpus-size dimension was found unnecessary given the ln scaling).

Note: this todo is `status: done` for the core dynamic timeout — the doc cleanup is the only remaining work.
