---
date: 2026-04-09
module: methodology
tags: [methodology, spec-review, adversarial-workflow, diminishing-returns, discipline]
problem_type: process
status: active
---

# When to stop reviewing a spec (or: the review loop ate my session)

## The problem

One NLSpec (`docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md`) went through four full review passes plus a fifth cosmetic one before the red team was ever dispatched. Each pass found real issues. None of them were nothing. And that was exactly the trap: because every pass was productive, I kept going. The scenario count walked from 30 to 38 to 47 to 51 to 59. Data model changed multiple times. P1s kept surfacing. Meanwhile, zero lines of implementation got written, and the user eventually had to ask the quiet part out loud — *"So we're still at the spec stage?"* — which is the session-orchestration equivalent of someone asking if you're OK.

Pass breakdown:

| Pass | Reviewer(s) | Findings | P1s |
|------|-------------|----------|-----|
| 1 | CodeRabbit, Gemini 2.5 Pro, Codex | 8 / 11 / 8 | multiple |
| 2 | CodeRabbit, Gemini 3.1 Pro | 2 / 11 | multiple |
| 3 | Codex (partial, salvaged from JSONL) | 2 | 1 |
| 4 | Codex (clean run) | 7 | 4 |
| 5 | CodeRabbit | 1 | 0 (cosmetic numbering gap) |

Pass 4 still surfaced four P1s, which locally looks like "we're not done". Globally, it was a signal that the review loop had become a substitute for implementation.

## The learning

Spec review has diminishing returns, and *knowing when to stop* is itself a skill. The deceptive part is that "the last pass still found issues" feels like a hard stop signal — you can't ship a spec with known P1s! — but almost all of those P1s are things the red team would catch anyway the moment they sit down to write feature files from the Done section. Contract gaps, ambiguous defaults, missing scenarios: these are exactly what the adversarial workflow is *designed* to surface. Paying a full review-pass tax to catch them before dispatch is doing the red team's job for them, badly, in the wrong seat.

### Stopping rule

Dispatch the red team after **two consecutive review passes where the findings are either:**

1. **Cosmetic** — wording, numbering, typos, formatting.
2. **Red-team-reachable** — contract gaps, missing scenarios, ambiguous defaults, anything a reviewer would find by trying to write a `.feature` file from the Done section.

**Continue reviewing only if the most recent pass surfaces something the red team would NOT catch**, such as:

- A cross-reference contradiction across distant sections of the spec.
- An unsafe assumption about an external dependency or existing code (e.g. "this file already exists and does X").
- A hidden quadratic or correctness footgun in the data model itself.
- A PII / safety / irreversibility concern that affects the DoD.

Everything else goes to the red team.

### Reviewer diversity matters more than reviewer count

No single reviewer caught everything on this spec. Running the same reviewer three times is cheap but low-signal. In this session:

- **CodeRabbit** — strongest on cosmetic and structural issues. Typos, field ambiguity, numbering gaps, section ordering. Fast, cheap, high precision, low ceiling.
- **Gemini 3.1 Pro** — strongest on cross-section logic contradictions. Caught parquet row multiplicity mismatch, the PII substring footgun, slug ordering ambiguity. These were the findings with the highest marginal value.
- **Codex** (when it ran cleanly) — strongest on spec × existing-code inconsistencies. Noticed that `split.feature` already existed and the spec was silently proposing to collide with it. No one else caught that.

A "one reviewer, three passes" strategy would have missed the most important class of findings (cross-section logic and spec-vs-codebase drift). The lesson: **rotate reviewers, don't stack them.** If you only have budget for two passes, make them two different models.

### The meta-learning: circuit breakers are not automatic

The real failure here wasn't any individual pass — each one was defensible in isolation. The failure was that the orchestrator (me) had no built-in circuit breaker for "this loop is too long, dispatch now". The user had to be the circuit breaker, and that's a smell. Loops that can only be broken from outside the loop are loops that will silently eat sessions.

The fix is a **pre-committed dispatch gate**, declared *before* the first review pass runs: "I will run at most two review passes, and then dispatch the red team regardless of what the second pass finds, unless it surfaces a contradiction class the red team cannot reach." Writing this down before starting the loop creates a forcing function that the loop can't quietly renegotiate with itself in the middle. Without the pre-commit, every individual "one more pass" decision looks locally rational, and the loop keeps going forever.

### What to do differently next time

1. Before starting review, declare the dispatch gate in writing (in the NLSpec header or the session plan).
2. Default to **two passes, two different reviewers**. Pick reviewers for diversity of failure mode, not name recognition.
3. After pass 2, classify the findings: cosmetic / red-team-reachable / red-team-unreachable. Only the third class justifies a pass 3.
4. If you catch yourself thinking "but the last pass still found P1s" — check whether those P1s are red-team-reachable. If yes, dispatch anyway. The red team will find them, and the spec will get better *with running test code attached*, which is strictly more information than another review pass.
5. Treat "the user asked if we're still at the spec stage" as a post-mortem trigger, not a prompt to defend the last pass.

## References

- Full per-pass review log: section 6 of `docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md`.
- Session-level summary: `docs/HANDOFF.md` entry for 2026-04-09.
- Related convention: adversarial process rules in `CLAUDE.md` (red/green team with information barrier).
