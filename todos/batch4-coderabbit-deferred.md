---
status: open
priority: P3
tags: [pr-review, deferred, batch4]
source: PR #5, #6, #7 automated bot review
issue_id: null
---

# Batch 4 / PR #5–#7 — deferred bot review items

Deferred findings from the 3-round bot review iteration on PRs #5, #6, and #7 (2026-04-07). P1/P2 items were fixed inline; these are P3/declined/nit items with rationale logged for future reference.

## Declined

- **Copilot PR #6 GFM table syntax (comments 3044017321, 3044017371):** Flagged `||` at row start → empty column. Declined as false positive; the raw file uses single `|` leading pipes and GitHub preview renders correctly. Re-check if a reviewer reports actual rendering issue.
- **Codex PR #7 step registration (comment 3048396549):** Claimed a `thinking_visibility` step module needed to be registered in `tests/cucumber.rs`. Declined — no such file exists; thinking-visibility scenarios are served by the existing `thinking_divergence.rs` step module which is already registered. 264/264 scenarios pass.
- **Gemini PR #7 single-pass refactor (comment 3048427055):** Suggested folding the `any_thinking`/`earliest_ts` derivation into the main parsing loop (`claude_code.rs:190-311`). Declined as a trade-off — the separate block keeps visibility-inference colocated and the cost is O(n) over an already-materialised Vec, dwarfed by the upstream JSON deserialisation. Reconsider if profiling ever shows it matters.

## Potential follow-ups (not blocking)

- Consider a `.editorconfig` or pre-commit hook to catch `<` in markdown outside of backticks — the `<run_context>` escaping came up 5 times across rounds 1+3. Could prevent future churn.
- The Boucle autonomous-session classifier (Phase 1 of `todos/autonomous-session-stratum.md`) should implement the "zero tools + Boucle markers" secondary rule called out in the W10–W12 investigation report Option B recommendation, not just the `queue-operation` marker check.
- Multilingual gating for `user-signal-analysis` is still open — see `todos/multilingual-text-techniques.md`.
