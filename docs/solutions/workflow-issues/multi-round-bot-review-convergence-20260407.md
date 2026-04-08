---
title: "Multi-round bot review iteration — convergence heuristics and polling cadence"
module: tooling
date: 2026-04-07
problem_type: workflow_issue
component: development_workflow
severity: low
applies_when:
  - "A PR has 2+ automated reviewers (Codex, Gemini, Copilot, CodeRabbit) with different re-review triggers"
  - "Reviewers post findings iteratively and the orchestrator must decide when to stop"
  - "Multiple PRs are open in parallel and need sequenced attention"
tags:
  - pr-review
  - codex
  - coderabbit
  - copilot
  - gemini
  - convergence
  - loop
  - workflow
---

# Multi-round bot review iteration — convergence heuristics and polling cadence

## Context

PRs #5, #6, #7 (Batch 4 Python techniques) ran through 4 rounds of automated review on 2026-04-07. Four bots with different behaviors made "are we done?" non-obvious:

- **Codex** re-reviews on *every push*. It is the most reliable convergence signal but also the noisiest — a stray whitespace commit will trigger a new pass.
- **Gemini, Copilot, CodeRabbit** typically run once per trigger (initial PR open, explicit `@mention`, or major rebase). They do not re-fire on every push, so absence-of-comment from them does not mean "they agree with the latest diff" — it may just mean "they never looked."
- **CodeRabbit** additionally auto-pauses after rapid commits; it must be resumed with `@coderabbitai resume` or it will silently stay quiet.

Without explicit heuristics the loop either terminates early (bots still had comments queued) or drags on indefinitely (waiting for reviewers that will not re-fire without a nudge).

## Guidance

### Convergence rule: "stable green at least twice, from at least two reviewers"

Stop iterating when **both** conditions hold:

1. The most recent push produced **zero new P1/P2 findings** from Codex (the per-push reviewer — this is your load-bearing signal).
2. At least one other reviewer (Gemini/Copilot/CodeRabbit) has weighed in on the *current* head SHA, or has been explicitly nudged with `@mention` and given one poll cycle to respond.

A single clean Codex pass is not enough — Codex sometimes notices things on round N+1 that it missed on round N (especially after a refactor shifts line numbers). Require **two consecutive clean Codex rounds** before declaring done. This is the "at least twice" rule: convergence is confirmed, not assumed.

### Polling cadence: /loop on an off-minute, ~13 minute interval

Use the `/loop` skill to poll for bot reviews rather than refreshing manually. Two tuning choices matter:

- **Interval: ~13 minutes.** Codex typically completes within 5–10 minutes of a push; CodeRabbit is 3–8; Gemini/Copilot vary. 13 minutes gives the slowest reviewer headroom on most pushes without burning too many polls.
- **Off-minute schedule.** Start the loop on a minute like `:07` or `:23`, not `:00` or `:15`. Round-minute polls collide with reviewer batch schedulers and frequently hit half-written review states where only 2 of 4 bots have posted. An off-minute offset gives a cleaner snapshot.

During each poll, fetch comments with `gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate` and diff against the previously-seen set — only act on *new* comment IDs.

### Reviewer-specific expectations

| Reviewer | Re-review trigger | Notes |
|---|---|---|
| Codex | Every push | Load-bearing convergence signal. Two consecutive clean rounds = done. |
| Gemini | Initial + `@gemini-code-assist` mention | Will not re-fire unaided. Nudge once mid-iteration if the diff has changed materially. |
| Copilot | Initial + major rebase | Rarely re-fires. Treat round-1 comments as one-shot. |
| CodeRabbit | Initial + `@coderabbitai resume` after rapid-commit pause | Check pause state after every round of 2+ commits. |

## Why this matters

The convergence question is where bot-review loops go wrong. Terminating early leaves P1 findings unaddressed on merged code; over-iterating wastes a full session babysitting a converged PR. The "two clean Codex rounds + at least one other reviewer on current head" rule gives a bounded stopping criterion that is *objective* (comment counts, not judgment calls) and *resilient* to the different trigger semantics of each bot.

The 13-minute off-minute polling cadence matters because naive polling produces false-negative snapshots — a `:00` check may catch a state where Codex has posted but CodeRabbit is mid-write, and the orchestrator can mistakenly conclude "CodeRabbit has no findings."

## When to apply

- Any PR with 2+ automated reviewers where you need to iterate
- Multi-PR sessions where you are sequencing attention across branches
- Any time you are tempted to "just wait a bit longer" — replace the vibes-based wait with the explicit rule

## Examples

### Declaring convergence (PR #7, round 4)

- Round 3 push → Codex: 2 P2 comments, Gemini: 1 P2, CodeRabbit: paused. Fixed, pushed round 4.
- Round 4 poll at `:07` after push: Codex: 0 new findings. CodeRabbit resumed via `@coderabbitai resume`, posted no P1/P2 at next poll.
- Round 5 poll at `:20`: Codex: 0 new findings (second consecutive clean). Gemini silent on current head, nudged via `@gemini-code-assist review`, returned nit-only.
- **Decision:** converged. Merge.

### Not-yet-converged trap (avoided)

- A single Codex-clean round after a large refactor looks done but is not. Rule enforces one more push-free poll cycle (or a trivial whitespace push) to confirm Codex really has nothing.

## Related

- `docs/solutions/workflow-issues/automated-pr-review-triage-workflow-20260404.md` — the fetch/triage/reply mechanics this builds on
- `docs/solutions/workflow-issues/pr-review-reply-discipline-and-declining-false-positives-20260407.md` — reply-to-every-comment discipline
- `docs/solutions/workflow-issues/atomic-per-round-commits-and-multi-pr-branch-routing-20260407.md` — commit and branch routing patterns for these loops
