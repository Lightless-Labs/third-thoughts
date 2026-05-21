---
title: "Add committed regression tests for archive plugin safety cases"
status: todo
priority: P2
tags: [archive, plugins, tests, privacy, safety]
source: codex-55-xhigh-review-2026-05-21
---

## Why

Codex 5.5 xhigh's Pi review found that the self-contained archive plugins rely on manual fixture smokes rather than committed regression tests. The smokes caught the big scary things today, but future-us deserves a less vibes-based safety net.

## Scope

Add shared tests for the bundled archiver behavior across the Pi, Claude Code, and Codex plugin packages:

- Missing option values and flag-looking option values fail clearly.
- Existing non-protective `.gitignore` inside a worktree gets a protective managed block.
- Symlinked parent directories cannot hide source/archive overlap.
- Drift and destination collision failures stay loud.
- Pi enrichment records the session header ID and `session_count: 1`, not every entry ID.
- Execution stays self-contained and does not require `middens` on `PATH`.

## Done

- [ ] Tests are committed under `integrations/` or a shared integration-test location.
- [ ] All three bundled `scripts/archive.mjs` copies are covered or verified identical before testing.
- [ ] Test command is documented in the relevant README or handoff.
- [ ] CI/local validation includes the new test command.
