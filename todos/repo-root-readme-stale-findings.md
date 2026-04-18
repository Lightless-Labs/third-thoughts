---
title: "Repo-root README cites superseded finding magnitudes"
status: todo
priority: P2
tags: [docs, readme, findings, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

The repo-root `README.md` still quotes the pre-stratification headline numbers for two findings that the 2026-04-14 full-corpus run materially revised. Project-level `CLAUDE.md` already carries the corrected values; the README does not. A first-time visitor lands on the README, not `CLAUDE.md`, so the stale figures are what gets cited externally.

## Refs

- `README.md:16-24` — "100% risk suppression" and "24.6x robust" claims
- `docs/HANDOFF.md:109-120` — same figures echoed in handoff doc
- `CLAUDE.md` (Third Thoughts) — already carries the corrected 99.99% and "provisional 2.15x" values
- `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md` — the run that revised them

## Fix

Update the repo-root README's findings table to match the project-level `CLAUDE.md`:

1. "100% risk suppression" → "99.99% risk suppression on visible-thinking sessions (N=4,518, 31,679 tokens, 2 leaks)"
2. "24.6x lift HSMM pre-failure state" → "HSMM pre-failure state — direction replicates (2.15x on 2026-04-14 run), 24.6x magnitude provisional pending W10–W12 exclusion"

Mirror the update in `docs/HANDOFF.md` so the two docs stay coherent.

## Why

From the codex pre-release review: the README is the first impression for a first-time reader. Shipping with already-superseded figures undermines trust in the project before the first command runs. The compound scoping rule in `CLAUDE.md` explicitly says "A finding that doesn't survive all four [axes] is not a finding" — continuing to lead with the unscoped numbers violates our own rule.

## Priority

P2 — not a beta-tag blocker (the tag can ship; the README is easy to patch), but should land before the beta gets wide circulation.
