---
title: "Atomic per-round commits and multi-PR branch routing during bot-review iteration"
module: tooling
date: 2026-04-07
problem_type: workflow_issue
component: development_workflow
severity: low
applies_when:
  - "Addressing review feedback across multiple files within a single round"
  - "Iterating on 2+ PRs in parallel where each lives on its own branch"
  - "Using CodeRabbit (which auto-pauses on rapid per-comment commits)"
tags:
  - pr-review
  - commits
  - branching
  - multi-pr
  - coderabbit
  - workflow
---

# Atomic per-round commits and multi-PR branch routing

## Context

On 2026-04-07, three PRs (#5, #6, #7) were iterating through bot review in parallel. Two temptations arise in this situation:

1. **Per-comment commits.** Fix each reviewer comment in its own commit. Feels atomic. Actually produces churn: 15 comments → 15 commits → CodeRabbit auto-pauses, Codex re-reviews 15 times, git log becomes unreadable.
2. **Interleaved branch switching.** Jump between PRs as comments arrive. Feels responsive. Actually thrashes context: the orchestrator loses track of which reviewer said what on which branch.

Both are wrong. The working pattern is **atomic per-round commits** (one commit per reviewer round per PR) and **sequential branch routing** (finish a round on one branch before switching).

## Guidance

### One commit per round per PR

A "round" = the batch of findings from one poll cycle across all reviewers on one PR. Fix them all, stage them together, write one commit with a structured message:

```
fix(middens): round 3 review feedback — PR #7

Addresses findings from Codex, Gemini, CodeRabbit:
- thinking_visibility: handle None case (Codex comment 3048396540)
- claude_code parser: clarify earliest_ts comment (Gemini 3048427050)
- docs/methods-catalog: fix broken anchor link (CodeRabbit 3048500100)

Co-Authored-By: ...
```

The message enumerates comment IDs so the reply-discipline references (see the related doc on reply discipline) have a SHA to point back to. One push triggers one Codex re-review, not fifteen.

### Batch fixes by file within the round

Within a round, group edits by file, not by reviewer. If Codex and Gemini both have comments on `claude_code.rs`, fix them in one edit pass. This avoids the failure mode where two commits touch the same file with conflicting approaches because the orchestrator forgot the earlier change.

### Sequential branch routing for multi-PR sessions

When N PRs are in flight, do not interleave. The routing rule:

1. Pick the PR with the *most recent* new findings (highest signal that the loop is live there).
2. Switch to its branch, complete one full round (fetch → fix → commit → push → reply), then poll all other PRs.
3. Only after the current PR's round is fully closed (committed, pushed, replies posted) switch to the next PR.
4. If mid-round a different PR starts looking urgent (e.g., a new P1 comment), **finish the current round first**. A 10-minute delay rarely matters; mid-round context loss always does.

Track in-flight PRs in a tiny status line in the session buffer:

```
PR #5 (feat/batch4-rustine): round 4 done, 2 consecutive clean Codex, awaiting 2nd reviewer on head
PR #6 (feat/batch4-middens): round 3 in progress — 5 Codex + 2 Copilot pending fix
PR #7 (feat/batch4-and-distribution-prep): round 4 done, declared converged
```

### CodeRabbit rapid-commit pause — budget for it

CodeRabbit auto-pauses after "too many commits too fast" (threshold is undocumented but ~3–4 commits within a few minutes reliably trips it). The atomic-per-round pattern naturally avoids this — one commit per round is well under the threshold. When a multi-commit round is genuinely unavoidable (e.g., a revert + fix), post `@coderabbitai resume` at the end of the round, not after each commit.

## Why this matters

- **Reviewer budget.** Every push spends Codex compute. Fifteen per-comment commits = 15 Codex runs; one per-round commit = 1. Over a multi-PR session that is a 10×+ efficiency gap.
- **Readable git log.** Post-merge, `git log --oneline` should tell the story of the PR in rounds, not in a blur of `fix typo` / `address coderabbit` entries.
- **Reply-reference integrity.** The reply-to-every-comment pattern says "fixed in <SHA>." If each comment has its own SHA, the replies work either way. If comments share a round SHA, that is fine — the commit message enumerates comment IDs, so the reverse lookup still works, and there are 15× fewer SHAs to chase.
- **Context preservation in multi-PR sessions.** Branch switching costs attention. Sequential routing bounds the cost to N switches per full iteration instead of N × comments_per_PR.

## When to apply

- Any PR with 3+ expected review comments per round
- Any session touching 2+ PRs in the same bot-review loop
- Whenever the temptation to "just push each fix as I make it" appears — resist

## Examples

### Good: PR #7 round 3 (2026-04-07)

One commit, `fix(middens): round 3 review feedback — PR #7`, touching 4 files, enumerating 6 comment IDs. Codex re-reviewed once. CodeRabbit stayed active. Round closed in a single fetch/fix/commit/push/reply cycle.

### Bad (avoided): the tempting alternative

Fifteen commits, one per comment, across two PRs interleaved. Would have: (a) tripped CodeRabbit pause, (b) burned 15 Codex runs, (c) produced a git log where round boundaries are invisible, (d) lost the mental model of "which reviewer said what on which branch."

## Related

- `docs/solutions/workflow-issues/multi-round-bot-review-convergence-20260407.md` — what "round" means and when to stop
- `docs/solutions/best-practices/pr-review-reply-discipline-and-declining-false-positives-20260407.md` — reply references to round SHAs
- `todos/batch4-coderabbit-deferred.md` — the deferred-items pattern this links into
