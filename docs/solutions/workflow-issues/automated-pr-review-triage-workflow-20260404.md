---
title: "Automated PR review triage workflow"
module: tooling
date: 2026-04-04
problem_type: workflow_issue
component: development_workflow
severity: low
applies_when:
  - "Addressing automated review comments from Codex, Copilot, Gemini, CodeRabbit"
  - "Multiple reviewers posting overlapping findings"
  - "Iterating through review rounds on a PR"
tags:
  - pr-review
  - codex
  - copilot
  - gemini
  - coderabbit
  - workflow
---

# Automated PR Review Triage Workflow

## Context

Learned from PR #3 (Python bridge) which received 28 comments across 2 rounds from 4 automated reviewers. Without a systematic process, it's easy to miss comments, double-fix overlapping issues, or fail to reply.

## Workflow

### 1. Fetch and triage

```bash
# Get all inline review comments
gh api repos/{owner}/{repo}/pulls/{n}/comments --paginate | \
  jq -r '.[] | "\(.id) [\(.user.login)] \(.path):\(.line) — \(.body | split("\n")[0][:80])"'

# Get review bodies
gh api repos/{owner}/{repo}/pulls/{n}/reviews --paginate | \
  jq -r '.[] | select(.body != "") | "[\(.user.login)] \(.state)\n\(.body | split("\n")[0][:100])"'
```

Triage into: P1 (blocks merge), P2 (should fix), P3 (cosmetic/doc-only). Group converging comments from different reviewers on the same issue.

### 2. Batch fix per round

- Fix all P1+P2 in one commit per round, listing every addressed comment in the commit message.
- Run full test suite before committing.
- One round = one push. This triggers re-reviews.

### 3. Reply to every comment

```bash
gh api repos/{owner}/{repo}/pulls/{n}/comments/{id}/replies -f body="Fixed in {sha}. {rationale}"
```

Reply even to comments you decline — explain the rationale. Review comments cannot be PATCHed after creation, so get the reply right the first time.

### 4. Wait for re-reviews

Each push triggers new review rounds. Poll:
```bash
gh api repos/{owner}/{repo}/pulls/{n}/reviews --paginate | \
  jq -r '.[] | select(.submitted_at > "{cutoff}") | "[\(.user.login)] \(.submitted_at)"'
```

Codex and Copilot usually respond in 1-3 min. Gemini in 3-7 min.

### 5. CodeRabbit quirks

- Free plan: summaries/walkthroughs only, no line-by-line comments
- Auto-pauses after rapid commits. Resume with `@coderabbitai resume` comment
- Re-reviews trigger on each push but may skip files "similar to previous changes"

## Timing observed (PR #3)

| Reviewer | Round 1 | Round 2 |
|----------|---------|---------|
| Codex | 4 comments | 2 comments (P1 timeout race, P2 python fallback) |
| Copilot | 13 comments | 3 comments (Windows temp file, PR desc, assertion) |
| Gemini | 4 comments | 2 comments (timeout race, JSON resilience) |
| CodeRabbit | Summary only | Auto-paused, no new findings |

Round 2 was significantly more focused — reviewers correctly identified that round 1 issues were addressed and found genuine new issues in the fix code itself.

## Why This Matters

Without this workflow, 28 comments across 4 reviewers becomes chaotic. The triage step is critical — multiple reviewers often converge on the same underlying issue (e.g., 3 reviewers all flagged the Windows python path). Grouping prevents duplicate fixes and produces cleaner commits.
