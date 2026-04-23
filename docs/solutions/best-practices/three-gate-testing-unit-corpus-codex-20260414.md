---
title: "Three-gate testing: unit tests, full-corpus run, and Codex xhigh review are all necessary"
date: 2026-04-14
category: best-practices
module: middens
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "A technique passes all unit tests but hasn't been validated on the real corpus"
  - "Deciding whether a feature is 'done' after the unit test suite goes green"
  - "Preparing a Codex review — choosing what to ask and how to frame it"
tags: [testing, corpus-validation, codex-review, scale-testing, performance, acceptance-gates, middens]
---

# Three-gate testing: unit tests, full-corpus run, and Codex xhigh review are all necessary

## Context

The middens project reached 332 passing Cucumber unit tests after implementing
timeout fixes for `prefixspan` and `cross-project-graph`. Green across the
board, so the obvious move was to ship.

Running `middens analyze corpus-full --all` on the actual corpus (13,423 sessions)
immediately revealed 4 additional technique timeouts that the unit tests had
never caught, plus ~130 session files silently dropped by the parser — visible
only at scale. A Codex xhigh review of the same changes (run before committing,
after "I think it works") caught 3 more bugs the tests also missed:
nondeterministic `project_lookup`, `--force` silently accepted without
`--timeout`, and `resolve_timeout` called before `needs_python` was computed.

All three gates were necessary. None was sufficient on its own.

## Guidance

### The three gates and what each catches

| Gate | What it catches | What it misses |
|------|----------------|----------------|
| **Unit tests** | Interface contracts on synthetic fixtures — correct API shape, expected output on small controlled inputs, regressions | O(n²) behaviour at scale, parser edge cases only present in real data, silent drops, cross-flag interaction bugs |
| **Full-corpus run** | Scale failures — techniques that time out on 13k sessions but run fine on a 10-session fixture, silently dropped files, real-world edge cases the fixtures don't cover | Logic bugs that don't manifest as timeouts or drops, flag wiring issues |
| **Codex xhigh review** | Algorithmic correctness, completeness of fixes, edge cases in CLI wiring — things a human reviewer might miss on a quick scan | Runtime behaviour, scale behaviour |

A technique that runs in under 1s on the fixture can still time out at 951s on
13,423 real sessions. Unit tests are structurally incapable of catching
O(n²) behaviour because the fixture is too small for the quadratic term to
dominate.

### Full-corpus run as scale acceptance gate

Run `middens analyze corpus-full --all` (or equivalent) before considering a
technique implementation complete. Watch for:

- Technique timeouts — any technique that exceeds the timeout threshold failed
  at scale even if tests passed
- Parser drop counts — if the parser silently skips session files, the count
  will be lower than expected; compare against a known session count baseline
- Error output — `--all` surfaces errors that individual technique runs might
  swallow

The full-corpus run is the only gate that exercises real O(n) and O(n²) paths
with production-grade data distribution. It can't be skipped just because the
unit tests are green.

### Codex xhigh review as logic correctness gate

Codex prompt structure that worked well:

1. Give the pre-fix commit hash and the post-fix commit hash
2. For each changed file, describe the algorithmic intent in plain English — not
   "I changed lines 42-67" but "this function is supposed to compute X, and the
   bug was that Y happened instead"
3. Ask Codex to focus on: (a) algorithmic correctness, (b) completeness of the
   fix, (c) edge cases in CLI wiring
4. Have it do manual diff review + targeted `cargo run` probes, not test runs

Don't ask Codex to run the test suite — it's already green. Ask it to find the
bugs the tests don't cover.

The review caught bugs that were invisible in the diff because they depended on
call order (`resolve_timeout` before `needs_python` computed) and on
combination semantics (`--force` without `--timeout`). These are logic bugs,
not test failures.

### Codex review timing

Run the Codex xhigh review *before* committing, after the implementation feels
done. Running it after the commit means fixing bugs in a separate commit, which
is fine, but running it before means the commit history is cleaner. The "I think
it works" moment is the right trigger — not "the tests are green" and not "I've
already pushed."

## Why This Matters

Shipping after unit tests alone leaves two classes of bugs in production:

1. **Scale bugs**: techniques that pass on 10 sessions, fail on 13,423. These
   are invisible until the first real corpus run and can make the tool appear
   broken to anyone who runs it on real data.
2. **Logic bugs**: incorrect call order, silently accepted invalid flag
   combinations, nondeterministic output. These are invisible to runtime
   testing unless the test specifically exercises the broken code path.

The combined cost of a full-corpus run + Codex review is roughly 30-60 minutes.
The combined cost of shipping scale bugs and logic bugs is "the tool doesn't
work on real data and nobody knows why." The math is not complicated.

## When to Apply

- Before any commit that modifies a technique's core logic or timeout handling
- Before releasing a technique from "beta/fixture-only" to "runs on real corpus"
- After any CLI flag change — flag wiring bugs are a Codex review specialty, not
  a unit test specialty
- After fixing a timeout: the fix might introduce a different O(n) behaviour
  that only shows up at scale

## Examples

### What unit tests caught (and what they missed)

```
# Unit tests: 332 passing
# Full-corpus run revealed:
#   - 4 additional technique timeouts (cross-project-graph at 951s, others similar)
#   - ~130 session files silently dropped by parser
# Codex xhigh review revealed:
#   - nondeterministic project_lookup (HashMap iteration order)
#   - --force silently accepted without --timeout (meaningless flag)
#   - resolve_timeout() called before needs_python computed (wrong order)
```

### Codex prompt structure that worked

```
Pre-fix commit: abc1234
Post-fix commit: def5678

Changes:
- middens/python/techniques/prefixspan_mining.py: Added early-exit when
  sequence count exceeds N. Intent: prevent O(n²) blowup on large corpora.
- middens/python/techniques/cross_project_graph.py: Added timeout guard.
  Intent: technique was running for 951s on full corpus; should exit at
  --timeout threshold.
- middens/src/main.rs: Added --force flag to bypass timeout floor/ceiling.
- middens/src/pipeline.rs: Added resolve_timeout() call.

Please review for:
(a) algorithmic correctness of the timeout fixes
(b) completeness — are there other code paths that could still time out?
(c) edge cases in CLI flag wiring (--force, --timeout, --no-python interactions)

Do a manual diff review and targeted cargo run probes. Don't run the test suite.
```

## Related

- `docs/solutions/best-practices/cli-flag-combination-validation-20260413.md` — the specific `--force`/`--timeout` bug this review caught
- `docs/solutions/best-practices/pattern-mining-fixtures-need-variation-20260406.md` — related lesson on fixture design
