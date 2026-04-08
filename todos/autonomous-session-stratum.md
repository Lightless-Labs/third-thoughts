# Autonomous Session Stratum — Phase 1 + Phase 2

**Created:** 2026-04-06
**Status:** Open (Phase 1 not yet started)
**Priority:** P1 — this is the NEXT concrete move after PR triage
**Source:** Pivot from PR #6 (corpus composition anomaly investigation) — user chose to promote Boucle contamination to a first-class session-type stratum rather than filter it out
**Follow-up on:** PR #6 (`feat/corpus-anomaly-w10-w12`). Land commits on that branch, don't open a new PR.

## Background

PR #6 investigation found that 100% of W10–W12 "interactive" sessions are Boucle autonomous-agent-loop iterations — zero tool calls, `queue-operation` type messages, framework references. Initial instinct: filter them out as contamination. User's better instinct: study them. Third Thoughts is literally a research project on AI agent behavior at scale, and autonomous agent loops are a distinct mode of operation that deserves its own stratum.

## The definition (elegant, framework-agnostic)

**`Autonomous = Interactive ∩ no_human_participation`**

where `no_human_participation` = zero messages with classification in `{HumanCorrection, HumanDirective, HumanApproval, HumanQuestion}`.

This sidesteps all framework-sniffing regex work. If there's an autonomous agent framework we've never heard of, it still gets classified as `Autonomous` the moment we observe "user messages exist but none are from a human." We don't need a Boucle detector, a LangGraph detector, a CrewAI detector — the structural absence of human signal is sufficient and falsifiable.

### Edge case to pin down in code

A real interactive session where the user only ever produces short `Unclassified` acknowledgements could look autonomous. If the session has ONLY `Unclassified` user messages (no `Human*` labels at all), that's ambiguous. Current rule (document in the classifier comment): **treat "zero Human* labels AND ≥1 user message" as autonomous** (not-human trumps not-known). This is a conservative call — we'd rather overcount Autonomous than undercount it, because the whole point is to stop contaminating the Interactive stratum.

## Phase 1 — Classifier (code)

### Changes required

1. **`middens/src/session.rs`** — add `Autonomous` variant to `SessionType` enum. Leave `Interactive` and `Subagent` unchanged.

2. **`middens/src/classifier/session_type.rs`** — extend the existing session-type classifier:

   ```rust
   // Existing: Subagent if any user message has a tool_use_id
   if has_subagent_signal(session) {
       return SessionType::Subagent;
   }
   // New: Autonomous if ≥1 user message AND zero Human* classifications
   if has_user_messages(session) && !has_any_human_classification(session) {
       return SessionType::Autonomous;
   }
   return SessionType::Interactive;
   ```

3. **`middens/src/corpus/discovery.rs` or `pipeline.rs` `--split`** — add a third bucket `autonomous` alongside `interactive` and `subagent`. Sessions with `SessionType::Unknown` should still go to both Interactive and Subagent buckets for backwards compatibility, OR we add an `unknown` bucket — your call, justify in a comment.

4. **Cucumber scenarios** (extend `tests/features/classifier/session_type.feature` or create a new one):
   - Scenario: session with mixed HumanCorrection + HumanDirective messages → classified Interactive
   - Scenario: session with only Unclassified user messages and no Human* labels → classified Autonomous
   - Scenario: session with tool_use_id on user messages → still classified Subagent (Subagent rule wins)
   - Scenario: session with both `Human*` labels AND tool_use_id → Subagent (Subagent rule still wins — document the precedence)
   - Scenario: empty session → Unknown (unchanged)

5. **Update the existing `--split` cucumber tests** to account for the new bucket. Count assertions on `corpus-split/` outputs will need to change.

6. **Re-run the split on the real corpus** to produce updated numbers:

   ```bash
   ./target/release/middens analyze corpus-split/ --split -o /tmp/three-way
   ```

   Expected outcome based on PR #6 evidence: 1,200+ sessions that were previously "interactive" in W10–W12 should move to `autonomous`. The new Interactive bucket should shrink dramatically in that window. Report the new weekly counts in an addendum to the investigation report.

### Phase 1 Done definition

- [ ] `SessionType::Autonomous` variant exists
- [ ] Classifier rule implemented and documented (including the "no Human* ∧ ≥1 user" edge case)
- [ ] `--split` produces `corpus-split/autonomous/` bucket (or equivalent)
- [ ] Cucumber: 5+ new scenarios covering the classification rules pass
- [ ] All 270+ existing scenarios still pass
- [ ] Re-run numbers on the real corpus added as an addendum to `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`
- [ ] Commits pushed to `feat/corpus-anomaly-w10-w12`
- [ ] PR #6 description updated to reflect it now contains code + classifier, not just a report

## Phase 2 — Comparative battery run (research)

Once Phase 1 is merged (or at least code-complete), run the full 23-technique middens battery on the new three-way split and write a comparative report.

### Questions to answer

1. **Risk suppression across strata** — does the 100% figure from PR #7 hold on Interactive? Is it defined on Autonomous at all (if autonomous loops never emit paired thinking/text messages, the metric is undefined — that's itself a finding)?
2. **Session-length distributions** — is there a characteristic iteration count per stratum? Autonomous loops showed a tight 5–19 message band in PR #6's sample; is this a universal autonomous-framework fingerprint or Boucle-specific?
3. **Tool diversity and entropy** — autonomous loops probably use a narrower tool set than interactive sessions. Markov transition matrices should look very different. Quantify the Shannon entropy gap.
4. **Correction patterns** — by definition autonomous has zero `HumanCorrection` events, so `correction-rate` should be 0. But what about structural corrections (tool_result with `is_error: true` followed by a different tool call)? That's a different signal worth looking at.
5. **Survival and change-point detection** — how does an autonomous loop "fail" vs how does an interactive session fail? Different shapes?
6. **HSMM behavioural states** — do autonomous loops show the pre-failure state signal at all? Different rates?
7. **Burstiness / Hawkes** — interactive sessions have human-driven pauses. Autonomous loops should be machine-paced (tighter burstiness, lower memory coefficient). Quantify.
8. **Information foraging / MVT** — the MVT violation finding says "agents under-explore." Does this hold when the "agent" is an autonomous loop with no human arbitrating exploration? Different baseline.

### Deliverables

- `docs/solutions/methodology/autonomous-stratum-comparative-analysis-20260406.md` (or later date)
- Each of the 8 questions above addressed with actual numbers from `middens analyze --split`
- Tables comparing Interactive / Subagent / Autonomous side by side for every technique that produces comparable findings
- Explicit statements about which existing findings (thinking suppression, MVT violation, HSMM pre-failure, session degradation) survive on which strata

### Phase 2 stopping criteria

- If Phase 2 turns out to produce boring or null results on Autonomous, that's still worth publishing as a negative finding. Do NOT spin it into a positive result.
- If any existing Third Thoughts finding turns out to have been driven entirely by Autonomous contamination (e.g., "session degradation" is actually just "autonomous loops always fail at iteration N"), that finding MUST be retracted or downgraded in the main report and in HANDOFF Key Findings.

## Cross-references

- `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md` — the investigation that motivated this work (Phase 0 evidence)
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — the prior precedent (same shape: a headline finding dissolves under a new stratification axis)
- `todos/multilingual-text-techniques.md` — the third stratification axis (language) that also needs remediation
- PR #7 (`feat/thinking-visibility-stratification`) — the second stratification axis (thinking visibility)
- HANDOFF.md "Compound scoping rule" — every future finding needs all four axes
