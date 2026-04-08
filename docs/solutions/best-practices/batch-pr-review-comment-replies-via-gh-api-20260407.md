---
module: pr-review-workflow
date: 2026-04-07
problem_type: best_practice
component: development_workflow
severity: medium
tags: [gh-cli, pr-review, automation, github-api, batching]
applies_when:
  - responding to automated PR review bots (Codex, Copilot, Gemini, CodeRabbit)
  - multiple review comments need individual replies
  - PR has dozens of inline comments across rounds
---

# Batch PR review comment fetch + reply via `gh api`

## Context

PRs on this repo accumulate comments from four automated reviewers (Codex, Copilot, Gemini, CodeRabbit) across multiple rounds. Clicking through the GitHub UI to reply to each comment is slow and error-prone. The default `gh pr view --comments` also misses inline review comments (they live on a different endpoint).

## Guidance

Fetch all inline review comments with pagination, triage with `jq`, then reply in batch:

```bash
# Fetch everything (inline review comments endpoint, paginated)
gh api repos/OWNER/REPO/pulls/NUMBER/comments --paginate > /tmp/pr-comments.json

# Triage: extract id, author, path, line, body
jq -r '.[] | "\(.id)\t\(.user.login)\t\(.path):\(.line)\t\(.body[0:120])"' /tmp/pr-comments.json

# Reply to a single comment
gh api repos/OWNER/REPO/pulls/NUMBER/comments/COMMENT_ID/replies \
  -f body="Addressed in <sha>: <one-line summary>"
```

For mass replies, drive `gh api` from a short Python loop (shell quoting breaks on multi-line bodies):

```python
import subprocess, json
replies = {
  12345: "Fixed in abc123 — renamed step file and added feature flag guard.",
  12346: "Declined — see thread; this is intentional per NLSpec section 3.",
}
for cid, body in replies.items():
    subprocess.run([
        "gh", "api",
        f"repos/OWNER/REPO/pulls/NUMBER/comments/{cid}/replies",
        "-f", f"body={body}",
    ], check=True)
```

## Why This Matters

- `--paginate` is mandatory on busy PRs — default page is 30 comments and silent truncation looks like "reviewer forgot to comment."
- The `/comments/{id}/replies` endpoint threads the reply under the original inline comment so reviewers see it in context. Top-level PR comments (`/issues/{n}/comments`) do not thread and reviewers often miss them.
- Batching via Python subprocess avoids zsh quoting hell on multi-line bodies with backticks, code blocks, or unicode.
- CodeRabbit auto-pauses after rapid commits; resume with `@coderabbitai resume` once the batch is pushed.

## When to Apply

- Any PR with >5 inline comments
- Any PR touched by automated reviewers
- Review rounds where comments cluster by file and can be addressed in one commit

## Examples

Full triage pipeline used on this session's batch-4 PRs:

```bash
gh api repos/lightless-labs/third-thoughts/pulls/42/comments --paginate \
  | jq -r 'group_by(.path)[] | "=== \(.[0].path) ===", (.[] | "  [\(.id)] \(.user.login): \(.body[0:80])")'
```

Grouping by path makes it obvious which files need atomic fix commits, and which comments converge across reviewers (strong signal — address first).
