---
title: PR Review Triage — #5, #6, #7
type: chore
status: active
date: 2026-04-07
---

# PR Review Triage — #5, #6, #7

## Overview

Triage and address bot review feedback across three open PRs, reply to every comment with rationale, and re-request reviews until converged (≥2 rounds per PR or clean on first pass). Defer non-blocking nits to `todos/`.

## Problem Frame

Three PRs are open with 32 inline review comments + review summaries from Gemini Code Assist, Copilot, Codex, and CodeRabbit. All three are MERGEABLE with green CI today. Goal: converge to merge-ready state by handling P1/P2 feedback and documenting rationale for deferrals.

- **#5** — `feat/batch4-and-distribution-prep` (17 inline comments, 4 reviews)
- **#6** — `feat/corpus-anomaly-w10-w12` (8 inline comments, 3 reviews)
- **#7** — `feat/thinking-visibility-stratification` (7 inline comments, 3 reviews)

## Requirements Trace

- R1. Every inline review comment gets a reply (fix + rationale, or deferral + todo link, or decline + rationale).
- R2. All P1 (correctness, security, data integrity) findings fixed inline.
- R3. All P2 (meaningful bugs, spec gaps) fixed inline OR explicitly deferred with a todo.
- R4. CI green and CodeRabbit SUCCESS on each PR head after final push.
- R5. Re-request `@codex review` + `@gemini-code-assist review` at least twice per PR (or until no new P1/P2 findings).
- R6. Deferred items land as files in `todos/` with YAML frontmatter.

## Scope Boundaries

- **Not** merging the PRs in this workflow — only driving them to merge-ready.
- **Not** starting Phase 1 of the Autonomous Session Stratum (follow-up work on #6's branch).
- **Not** rewriting any finding, spec, or research conclusion — only addressing bot feedback on the shipped artifact.

## Context & Research

### Relevant Code and Patterns

- `docs/HANDOFF.md` "PR review iteration" section — the canonical triage discipline for this repo.
- `todos/batch3-coderabbit-deferred.md` — precedent for how deferred bot feedback is logged.
- Reviewer behaviour from HANDOFF:
  - Codex re-reviews on every push (expect 3-6 rounds).
  - CodeRabbit, Gemini, Copilot review once per trigger; must `@mention` to re-run.
  - CodeRabbit nests nitpicks inside collapsible sections of its main comment body — must expand + triage.

### Institutional Learnings

- Three-bot convergence = definitely real; stop second-guessing.
- Don't adapt tests to match unauthorized API deviations; amend spec or reject.
- Stopping rule: all P1s fixed, tests pass, CR SUCCESS, merge CLEAN, no new Codex review in ~15min.

## Key Technical Decisions

- **Batch fixes per PR** — one atomic commit per round per PR listing all addressed items; no commit-per-comment churn.
- **Reply to every comment** even when declining — silence gets interpreted as "will address later."
- **Process PRs in parallel** where reviews don't interact (they don't — different branches, different scopes).
- **Merge order when ready**: #6 and #7 standalone; #5 standalone. No cross-branch dependency. User may choose to hold #6 for Phase 1 follow-ups; do not merge without asking.

## Open Questions

### Deferred to Implementation

- Which specific comments are P1 vs P2 vs nit — determined per-comment during triage.
- Whether any comment surfaces a spec gap requiring NLSpec amendment vs a simple code fix.
- Whether to consolidate Batch 4 deferred items into a new `todos/batch4-coderabbit-deferred.md` or append to the existing Batch 3 file.

## Implementation Units

- [ ] **Unit 1: Fetch and triage all review feedback**
  - **Goal:** Build a single triage table (PR / file / line / reviewer / severity / action) covering all 32 inline comments + review body nitpicks from all 3 PRs.
  - **Files:** Scratch triage notes; no repo file yet.
  - **Approach:** `gh api repos/.../pulls/{n}/comments --paginate` per PR; `gh pr view {n} --json reviews` for review bodies; expand CodeRabbit nested nitpick sections. Classify each as P1/P2/P3/nit and Fix/Defer/Decline.

- [ ] **Unit 2: Address PR #5 feedback (Batch 4)**
  - **Goal:** Fix P1/P2 on Batch 4 + distribution prep.
  - **Files:** TBD from triage — likely `middens/python/techniques/*.py`, `middens/src/bridge/embedded.rs`, `middens/Cargo.toml`, `middens/tests/features/techniques/python_batch4.feature`.
  - **Approach:** Batch fixes into one commit on `feat/batch4-and-distribution-prep`. Reply to each comment with resolution rationale.
  - **Verification:** `cargo test` green, `cargo build --release` clean, CR re-review SUCCESS.

- [ ] **Unit 3: Address PR #6 feedback (corpus anomaly doc)**
  - **Goal:** Fix P1/P2 on the W10–W12 Boucle investigation report.
  - **Files:** TBD — likely `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`, `todos/autonomous-session-stratum.md`.
  - **Approach:** Doc-only PR; feedback likely on numerical claims, framing, reproducibility notes.
  - **Verification:** CR re-review SUCCESS, no broken internal links.

- [ ] **Unit 4: Address PR #7 feedback (thinking-visibility stratification)**
  - **Goal:** Fix P1/P2 on the thinking-visibility parser flag + guard.
  - **Files:** TBD — likely `middens/src/parser/*`, `middens/src/techniques/thinking_divergence.rs`, session model, relevant tests.
  - **Approach:** Parser heuristic correctness is the highest-risk area (classification drives the 100% finding). Any feedback there is P1 by default.
  - **Verification:** `cargo test` green, re-run `middens analyze` spot-check on a known-visible session, CR re-review SUCCESS.

- [ ] **Unit 5: Log deferred items as todos**
  - **Goal:** For every P3/nit/deferred decision, create or append a `todos/` file with YAML frontmatter (status, priority, issue_id, tags, source PR).
  - **Files:** `todos/batch4-coderabbit-deferred.md` (new or reuse existing batch3 pattern), possibly additional per-scope files.
  - **Approach:** Link from PR replies to the todo file so reviewers see where the item lives.

- [ ] **Unit 6: Re-request reviews — Round 2**
  - **Goal:** Trigger fresh `@codex review` + `@gemini-code-assist review` on each PR after fixes land.
  - **Files:** none (PR comments only).
  - **Approach:** Post re-review requests. Wait for completion. Re-enter triage (Units 1–5) for any new P1/P2.

- [ ] **Unit 7: Re-request reviews — Round 3 (conditional)**
  - **Goal:** Third pass only if Round 2 surfaces new P1/P2.
  - **Approach:** Same as Unit 6. If Round 2 is clean, skip and declare converged.

- [ ] **Unit 8: Update HANDOFF.md status**
  - **Goal:** Mark each PR as merge-ready (or not) with one-line summary.
  - **Files:** `docs/HANDOFF.md`.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| CodeRabbit auto-pauses after rapid commits | `@coderabbitai resume` per HANDOFF convention |
| New Codex round introduces P1 after "done" declared | Stopping rule: ~15min quiet window before declaring converged |
| Parser heuristic feedback on #7 invalidates the 100% stratified finding | Treat as research-grade P1: stop, re-run, update finding or retract |
| Bot refuses repeated comment edits | Post a new reply instead of editing |

## Sources & References

- `docs/HANDOFF.md` — PR review iteration section
- `todos/batch3-coderabbit-deferred.md` — deferred-item precedent
- PR #5, #6, #7
