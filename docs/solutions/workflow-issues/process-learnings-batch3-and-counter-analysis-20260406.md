---
title: "Process learnings from PR #4 review loop, multi-agent delegation, and the counter-analysis pattern"
date: 2026-04-06
category: workflow-issues
module: orchestration
problem_type: workflow_lesson
component: multi_agent_process
severity: high
applies_when:
  - "Running multi-round automated PR review iteration (CodeRabbit, Gemini, Copilot, Codex)"
  - "Dispatching sub-agents for read-heavy research tasks"
  - "Orchestrating adversarial red/green development across multiple CLI models"
  - "Producing outward-facing findings that will be published or filed upstream"
tags: [pr-review, delegation, coderabbit, codex, gemini, copilot, opencode, subagents, adversarial, counter-analysis, compound-engineering]
---

# Process learnings — Batch 3 PR loop and the GH#42796 counter-analysis

## Context

The 2026-04-06 session shipped Batch 3 of the Python technique ports as PR #4
(merged at `9eca691`, completing 13/13 techniques) and ran a two-stage
replication study of Laurenzo's GH#42796 "Claude Code reasoning regression"
claim — first a sympathetic replication
(`~/claude-reasoning-performance-analysis/report.md`) and then an adversarial
counter-analysis (`~/claude-reasoning-performance-counter-analysis/report.md`).

The PR went through six rounds of automated review iteration. Commits
`34f32d1`, `6ec82cd`, `7a65047`, `19825bb`, `bdd2c3a`, `ad6ba24`, `b590e4b`
each address one round of reviewer findings (CodeRabbit local + Gemini +
Copilot + Codex r2 through r6). The session also exposed two sub-agent
refusal incidents and mis-dispatched several OpenCode invocations before
the dispatch pattern was normalised in `e8e4cf9`.

These are the durable process learnings from that arc.

## Learnings

### 1. Reviewer asymmetry: Codex re-reviews; Gemini/Copilot do not

**Observation.** Codex re-runs a full review on every push to a PR. Gemini
and Copilot fire once on the initial commit and stay silent thereafter
unless you dismiss + re-request explicitly. CodeRabbit auto-pauses after
rapid pushes and needs `@coderabbitai resume`.

**Mechanism / why.** Each bot has its own trigger model. Codex binds to the
push event; Gemini and Copilot bind to PR open / first review-requested.
The asymmetry is invisible if you only watch the GitHub UI — you see "no
new comments" and assume convergence, when really three of four reviewers
are no longer participating.

**Concrete rule.** Treat Codex as the only continuous reviewer once round 1
is in. Gemini/Copilot's silence after a fix push is *not* validation. If
you need a second pair of eyes on a late-round fix, dispatch it manually
(subagent diff review) rather than waiting for re-review. Do not block
merge waiting for Gemini/Copilot to come back.

**Evidence.** PR #4 commits `34f32d1` (CodeRabbit local), `6ec82cd`
(Gemini + Copilot + Codex r1 batched), then `7a65047` … `b590e4b` (Codex
r2–r6, no Gemini or Copilot participation). HANDOFF.md §"PR review
iteration" point 1.

### 2. Run CodeRabbit locally before opening the PR

**Observation.** The local `coderabbit review --plain --base origin/main`
pass produced 20 findings on Batch 3 *before* the PR was opened. All 20
were fixed in `34f32d1` and never reached the remote review.

**Mechanism / why.** Remote review rounds are expensive: each one consumes
a real human-time wall-clock window (~15 min for Codex to land), introduces
context shift, and costs model quota. A local lint pass collapses the
first round into a single commit and changes the remote conversation from
"here are 20 things" to "here are the 6 things the local lint missed".

**Concrete rule.** Local CodeRabbit is mandatory before PR open for any
non-trivial PR. Treat the remote round as a *second* opinion, not the
first.

**Evidence.** Commit `34f32d1` "fix(batch3): address CodeRabbit P1
findings" lands before PR #4 is opened; the next commit `6ec82cd` is the
first round that mixes remote reviewer feedback. HANDOFF.md §"PR review
iteration" point 3.

### 3. Three-way reviewer confirmation = stop second-guessing

**Observation.** When Gemini, Copilot, and Codex independently flag the
same line with the same diagnosis, the bug is real every time. Batch 3
hit this twice: the Phase 1 filter bug and the NCD single-stream guard,
both in the round-1 batch (`6ec82cd`).

**Mechanism / why.** The three reviewers use different model families,
different prompt scaffolding, and different code-traversal heuristics. A
shared hallucination across all three is vanishingly unlikely; convergent
flagging is high-precision signal. Time spent re-reading the line to
"verify" the convergent verdict is wasted — an experienced human reviewer
would already have called it.

**Concrete rule.** If three independent bots flag the same line with the
same diagnosis, fix it in the next commit without re-litigation. Reserve
deliberation budget for the cases where reviewers disagree.

**Evidence.** Commit `6ec82cd` "fix(batch3): address PR #4 review comments
(Gemini + Copilot + Codex)" — both bugs were fixed inline, no debate.

### 4. Stopping rule for PR review loops

**Observation.** Without an explicit stopping rule, the loop wants to run
forever — there's always one more nit, one more "consider", one more bot
that hasn't weighed in. The user's mid-round corrective ("Round 7? You're
overdoing it xD") was the human signal that compulsive perfection had
overshot.

**Mechanism / why.** Each round has a real fixed cost (commit churn, CI
runs, context window, reviewer quota) and diminishing returns. After
round ~5 the per-round yield on Batch 3 was a single P2-grade finding.
The loop terminates correctly when the *signal* drops below the *cost*,
not when the comment stream goes empty.

**Concrete rule.** Merge when all five hold:
(a) all P1s from the current round fixed;
(b) all tests pass;
(c) CodeRabbit status is SUCCESS;
(d) merge state is CLEAN;
(e) no new Codex review has landed in ~15 minutes.
Do not wait longer than 15 minutes for additional bot activity. Defer
P3/nits to a follow-up todo file rather than burning a round.

**Evidence.** Commits `7a65047` … `b590e4b` show the round-by-round
descent from many findings to one. HANDOFF.md §"PR review iteration"
point 6. `todos/batch3-coderabbit-deferred.md` is the deferral sink.

### 5. Sub-agent refusal pattern under context_window_protection

**Observation.** Twice this session, a general-purpose `Agent` subagent
dispatched to do data analysis refused with a "can't use Bash/Read, don't
have ctx_execute" bind. The cause: sub-agents inherit a stricter
`context_window_protection` system reminder than the main session, which
directs them to route through MCP `ctx_execute*` tools — but those tools
are *not* registered in the sub-agent tool list in this environment. The
sub-agent therefore enters a constraint conflict and refuses.

**Mechanism / why.** The protection reminder is loaded ahead of the tool
manifest in sub-agent contexts, and the sub-agent reasons from the
reminder rather than the (smaller) actual tool set. Re-dispatching with
louder "please just do it" framing does not help: the new sub-agent reads
the same reminder and reaches the same refusal.

**Concrete rule.** For data-analysis work, do not dispatch general-purpose
`Agent` sub-agents. Either (a) run inline in the main session via
`ctx_execute` (which IS available there), or (b) use `Explore` sub-agents
for read-heavy research. Reserve general-purpose sub-agents for
write-heavy coding tasks where Edit/Write are unambiguously authorised.
If a refusal happens once, do not re-dispatch — switch lane.

**Evidence.** HANDOFF.md §"Sub-agent refusal pattern". The adversarial
counter-analysis at `~/claude-reasoning-performance-counter-analysis/report.md`
was ultimately produced inline in the main session after two sub-agent
refusals, not by a sub-agent.

### 6. Adversarial spec amendments stay in the spec, not the code

**Observation.** Batch 3 had three rounds of mid-review NLSpec amendments
(Phase 1 / Phase 3 separation, the `min_projects` reconcile, the NCD
symbol-alphabet definition). Every one was routed through the spec file
at `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md`
and then re-broadcast to red and green teams independently. The
orchestrator never edited test code or implementation directly.

**Mechanism / why.** The information barrier between red and green only
holds if the spec is the single source of truth. As soon as the
orchestrator patches a test or an implementation directly, the barrier
collapses: the patched side now contains information the other side
doesn't, and the red/green confrontation degrades into a three-party
debug session led by the orchestrator's prior. Routing through the spec
preserves the falsifiability of each side's output.

**Concrete rule.** When red/green disagree, classify the disagreement as
(i) spec ambiguity, (ii) red bug, (iii) green bug, or (iv) improvement.
Only (i) is the orchestrator's to fix, and the fix lives in the spec.
(ii)/(iii) get routed back to the originating team with PASS/FAIL only —
never with assertion text or error messages. (iv) gets parked.

**Evidence.** Commits `61f602b` (red), `97a3c99` (green), `34f32d1`/`6ec82cd`
(orchestrator-driven fixes that all touch implementation, never tests,
because the test surface was authoritative). HANDOFF.md §"Adversarial
development".

### 7. Delegation tool selection — always have two green-team options

**Observation.** This session mis-dispatched OpenCode several times before
landing on the correct invocation pattern (commit `e8e4cf9`). Failure
modes seen: stuck Kimi processes, `-s false` shell-flag contamination
creating stray `:false/` directories, `/tmp/*` permission rejection from
OpenCode's `external_directory` policy, empty output files from missing
`wait` after backgrounded `&` dispatch (originally misdiagnosed as
"SQLite WAL conflict"), and silent failure on the stale `minimax/minimax-m2.7`
model ID. Codex was not available as a fallback because of quota limits.

**Mechanism / why.** OpenCode is fast but flaky and has many footguns;
Gemini 3.1 Pro is reliable but cannot serve both red and green teams
(same-model contamination violates the adversarial information barrier);
Codex is reliable but quota-rationed. A single-source green-team plan is
fragile because any one of the three failure modes will block the batch.

**Concrete rule.** Before starting a batch, validate two green-team
configurations end-to-end against the shared contract: a primary
(typically Kimi K2.5 via OpenCode) and a fallback (typically Minimax M2.7
or GLM 5.1). Cap parallel OpenCode dispatches at 2–3 and always `wait`
after backgrounded `&`. Never use `-s false` for OpenCode (it's a Gemini
flag). Always `--format json` + `jq -r 'select(.type == "text") | .text'`
for clean output. Use `-f <file>` to attach context, never reference
`/tmp/*` paths in prompt text.

**Evidence.** Commit `e8e4cf9` "docs(HANDOFF): correct OpenCode dispatch
pattern after Batch 3 misdiagnoses". HANDOFF.md §"OpenCode dispatch
pattern" and §"OpenCode gotchas" capture the validated invocation.

### 8. The counter-analysis pattern — adversarial pass before publishing

**Observation.** A sympathetic replication agent confirmed three of
Laurenzo's GH#42796 claims (signature↔thinking r=0.94, redaction rollout
0%→82%, Write%-of-mutations "doubled") and recommended filing a PR
upstream against `anthropics/claude-code`. An adversarial counter-analysis
run inline in the main session attacked the same data with seven probes,
four of which executed successfully, and *all four landed*:
- C3 (Write doubled) is dead — proper weighting gives +5pp not 2x;
  permutation p=0.445 at n=7 weeks.
- C2 (redaction rollout) fails significance — permutation p=0.20, and
  the curve is non-monotonic (W10=64%, W11=16%, W12=82%) in ways
  inconsistent with a staged rollout.
- C1 (signature correlation) is power-starved in the W12 tail — only
  77 paired samples, 95% CI ±0.22, no power to distinguish 0.72 from 1.0.
- A composition anomaly (W10→W11 sessions 27→1230 while tools/session
  collapsed 572→8.9) is the dominant signal; population drift mechanically
  reproduces every "regression" the sympathetic report saw.

The recommendation flipped from "file upstream" to "do not file from this
corpus".

**Mechanism / why.** Sympathetic replication has a confirmation prior
baked into the prompt — "see if the claim holds". It will preferentially
find supporting evidence and undercount disconfirming structure. A single
sympathetic read is not a replication; it is a rephrasing. An adversarial
pass with the explicit goal of *killing* the claim is the cheapest known
mechanism for catching false positives before they leave the workstation.
This is the same epistemic move as three-way reviewer confirmation
(learning 3), applied to research findings instead of code review.

**Concrete rule.** Any outward-facing finding — anything that would be
published, filed upstream, or used as a foundation for a downstream
decision — must pass an adversarial counter-analysis run in a separate
context from the sympathetic replication. The counter-analysis prompt
must be framed as "kill this claim", not "verify this claim". If the
counter-analysis lands any P1 attack, the finding is not ready to ship.

**Evidence.** `~/claude-reasoning-performance-analysis/report.md`
(sympathetic, recommends filing) vs
`~/claude-reasoning-performance-counter-analysis/report.md` (adversarial,
recommends not filing). HANDOFF.md §"GH#42796 replication" and §"Corpus
composition anomaly (W10→W11)". Commit `3bff886` documents the reframe.

## References

**Commits (chronological, Batch 3 + post-merge):**
- `61f602b` — red team Cucumber tests for Batch 3
- `97a3c99` — green team implementation
- `e8e4cf9` — HANDOFF correction for OpenCode dispatch pattern
- `34f32d1` — local CodeRabbit P1 fixes (pre-PR)
- `6ec82cd` — round 1 (Gemini + Copilot + Codex batched)
- `7a65047` — round 2 (Codex)
- `19825bb` — round 3 (Codex)
- `bdd2c3a` — round 4 (Codex)
- `ad6ba24` — round 5 (Codex)
- `b590e4b` — round 6 (Codex, final)
- `9eca691` — squashed merge of PR #4
- `3bff886` — HANDOFF post-merge with replication findings

**Files:**
- `/Users/thomas/Projects/lightless-labs/third-thoughts/docs/HANDOFF.md` — §"PR review iteration", §"Sub-agent refusal pattern", §"OpenCode dispatch pattern", §"GH#42796 replication", §"Corpus composition anomaly (W10→W11)"
- `/Users/thomas/Projects/lightless-labs/third-thoughts/middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md` — the spec amended three times mid-review
- `/Users/thomas/Projects/lightless-labs/third-thoughts/todos/batch3-coderabbit-deferred.md` — deferral sink for P2/P3 findings
- `~/claude-reasoning-performance-analysis/report.md` — sympathetic replication
- `~/claude-reasoning-performance-counter-analysis/report.md` — adversarial counter-analysis
- `~/.claude/skills/opencode-cli/` — validated OpenCode dispatch skill

**Related solutions:**
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — prior instance of the same population-drift failure mode that the counter-analysis re-discovered in W10→W11
- `docs/solutions/best-practices/cross-project-claim-verification-*.md` (commit `8429c58`) — earlier compound learning that this session extends with the explicit adversarial-pass requirement
