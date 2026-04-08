---
date: 2026-04-06
problem_type: methodology
severity: high
status: investigated
module: middens/techniques/thinking-divergence
tags: [stratification, thinking-blocks, risk-suppression, beta-header, redact-thinking]
related:
  - todos/redact-thinking-header-correction.md
  - docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md
---

# Thinking-visibility stratification for the 85.5% risk-suppression finding

## Problem

On 2026-02-12 Anthropic rolled out the `redact-thinking-2026-02-12` beta header
which hides thinking blocks from the Claude Code UI to reduce latency.
Crucially, this is **UI-only**: thinking is still happening under the hood,
but it is no longer written to local session transcripts.

Any middens technique that counts thinking blocks in transcripts — primarily
`thinking-divergence`, which underlies the 85.5% risk-suppression finding —
therefore measures *transcript presence of thinking*, not *whether the model
was reasoning privately*. Sessions captured after the rollout look like "no
thinking at all", which silently pulls down the suppression-rate denominator
and may inflate or deflate the apparent rate depending on the composition of
the visible-vs-redacted split.

The headline 85.5% claim needs to be scoped honestly to
`thinking_visibility == Visible` sessions only.

## What was implemented

1. **New `ThinkingVisibility` enum** in `middens/src/session.rs` with
   variants `Visible`, `Redacted`, `Unknown` (default). Placed on `Session`
   (not `SessionMetadata`) because it is a derived property of the entire
   message stream and techniques must branch on it frequently.

2. **Heuristic population in the Claude Code parser**
   (`middens/src/parser/claude_code.rs`):
   - Any assistant message has a `thinking` block → `Visible`.
   - No thinking blocks AND earliest message timestamp < 2026-02-12T00:00:00Z
     → `Visible` (pre-rollout default).
   - No thinking blocks AND earliest message timestamp ≥ 2026-02-12T00:00:00Z
     → `Redacted`.
   - Else (no timestamps) → `Unknown`.

   Limitations documented in-code: a session could be post-cutoff with the
   beta header disabled (→ should be Visible but classified as Redacted) or
   pre-cutoff with coincidentally zero thinking (→ classified Visible,
   benignly included). The Unknown bucket preserves uncertainty.

3. **`thinking-divergence` technique guard** in
   `middens/src/techniques/thinking_divergence.rs`:
   - `Redacted` sessions are skipped entirely and counted under
     `skipped_redacted_sessions`.
   - `Unknown` sessions are included but also counted under
     `unknown_visibility_sessions`.
   - Both counters appear as findings in the output.
   - When either is > 0, the summary gains a suffix:
     `(computed on N visible sessions; K skipped as thinking-redacted;
     U with unknown visibility)`.

4. **Cucumber scenarios** added to
   `middens/tests/features/techniques/thinking_divergence.feature`:
   all-visible, all-redacted, and mixed fixtures. Step definitions in the
   new file `middens/tests/steps/thinking_visibility.rs`.

## Re-run on the real corpus — results

Run performed 2026-04-06 against the interactive corpus at
`corpus-split/interactive/` (2,594 symlinks, 1,932 still reachable —
662 symlinks are stale references to rotated sessions). Of the 1,932
reachable files, 1,834 parsed successfully as Claude Code sessions.

Command:
```bash
./middens/target/release/middens analyze /tmp/interactive-valid \
    -o /tmp/thinking-rerun --techniques thinking-divergence
```

### Raw results

```
SUMMARY: Analyzed 828 sessions with thinking blocks.
         Average risk suppression rate: 100.00%.
         Overall thinking-to-text divergence ratio: 111.36.
         (computed on 828 visible sessions; 1006 skipped as
          thinking-redacted; 7 with unknown visibility)

suppression_rate:            1.0
divergence_ratio:            111.3553
sessions_with_thinking:      828
messages_with_both:          209
total_risk_tokens:           4819
suppressed_tokens:           4819
sessions_analyzed:           828
skipped_redacted_sessions:   1006
unknown_visibility_sessions: 7
```

### Interpretation

**Sample composition:**
- 1,834 sessions parsed from the reachable interactive corpus
- 828 (45.1%) classified as `Visible` — first message before 2026-02-12
  or at least one thinking block present
- 1,006 (54.9%) classified as `Redacted` — first message on or after
  2026-02-12 AND no thinking blocks present
- 7 (0.4%) `Unknown`

**Headline number: 100% suppression on visible-only sessions, not 85.5%.**

**Why the number moves UP, not down:**

The old 85.5% was computed on a mixed corpus where many sessions had ZERO
thinking blocks (because the beta header was set). Sessions with no
thinking trivially score 0% suppression (no risk tokens found, nothing to
suppress), which drags the per-session mean DOWN. When those
redacted-but-counted sessions are properly excluded from the denominator,
the rate moves to 100% across 4,819 risk-token observations in 209 paired
messages.

**What the 100% claim actually means:**

Across 209 messages that have BOTH a thinking block and a text response,
every risk token (case-insensitive substring match from a fixed 55-token
English lexicon — authoritative list in `RISK_TOKENS` at
`middens/src/techniques/thinking_divergence.rs`, covering risk/uncertainty
words (`risk`, `concern`, `worry`, `problem`, `issue`, `error`, `fail`,
`wrong`, `careful`, `uncertain`, `maybe`, `might`, `however`, `but`,
`although`, `caveat`, `warning`, `danger`, `tricky`, `edge case`,
`caution`, `potential`, `possibly`, `unclear`); safety/security words
(`unsafe`, `malicious`, `exploit`, `untrusted`, `vulnerability`, `flaw`,
`security`, `leak`, `sensitive`, `confidential`, `hazard`, `threat`,
`harm`, `insecure`, `peril`, `jeopardy`, `suspicious`, `unauthorized`,
`leakage`); and credential words (`password`, `secret`, `token`,
`credential`, `apikey`, `key`, `access`, `auth`))
that appears in the thinking block is **absent from the paired
user-facing text**. This is a strong but narrowly-scoped claim about
risk-framed vocabulary crossing the thinking/text boundary. It is
consistent with the model preferring to reason about risk internally and
emit more neutral external language, rather than suppressing the concept
entirely.

### Caveats compounding with this result

1. **Corpus contamination (W10–W12)** — per
   `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md`,
   a substantial fraction of post-W09 "interactive" sessions are Boucle
   autonomous-agent-loop iterations, not real interactive Claude Code
   sessions. Boucle sessions have zero tool calls and typically no
   thinking blocks, so they most likely classify as `Redacted` and are
   already being dropped by the stratification above — **but this should
   be verified** by re-running the technique on a corpus that explicitly
   excludes `queue-operation` type sessions.

2. **Stale symlinks (662 files unreachable)** — the `corpus-split/`
   stratification was built from symlinks that have since been rotated.
   The 1,932-session sample is a non-random 74% slice. Low risk because
   rotation is time-based, not content-based, but the 45/55 visible/
   redacted split may be slightly biased.

3. **English-only confound** — `thinking-divergence` uses literal English
   `RISK_TOKENS`. See `todos/multilingual-text-techniques.md`. Non-English
   sessions will classify as 0% suppression regardless of actual content.
   The honest scope is
   **`language=en AND thinking_visibility=Visible AND NOT contaminated_by_Boucle`**.

## Recommendation

1. **Retract the 85.5% figure** from all reports. Replace it with the
   stratified 100% figure, explicitly scoped to visible-thinking sessions.

2. **Update `CLAUDE.md` "Key Findings" table** — change the
   "85.5% risk suppression" row to:

   > **100% risk-token suppression** on sessions with visible thinking
   > and paired text (N=828 sessions, 4,819 risk tokens observed across
   > 209 paired messages). Requires thinking blocks in the transcript
   > (pre-2026-02-12 or beta-header opt-in); post-rollout sessions with
   > no thinking are excluded automatically by the stratification guard.

3. **Re-run on a Boucle-filtered corpus** once the Boucle filter lands
   (see the corpus-composition-anomaly investigation report). Expected
   effect: small — Boucle sessions have no thinking blocks and are
   already in the `Redacted` bucket.

4. **Stop trying to replicate "85.5% on the mixed corpus."** That number
   was an artifact of mixing Visible and Redacted sessions. The correct
   baseline is 100% on the stratified visible-only sample; deviation
   from that in future runs would be the interesting finding.

5. **Treat 100% as an upper bound, not a population parameter.** The
   observation is narrow (209 paired messages, single research corpus).
   The per-observation confidence interval at n=4,819 is tight in
   absolute terms but the population-level generalization is not
   supported — this is a within-corpus observation.

## Status of the 85.5% headline

**Superseded.** The 85.5% figure was a mixed-corpus artifact. The
correctly-stratified figure on visible-thinking sessions is
**100% risk-token suppression across 4,819 observations in 209 paired
messages from 828 sessions**, subject to the three caveats above
(corpus contamination, stale symlinks, English-only scope). The
technique now auto-stratifies, so re-runs produce the correctly-scoped
number by construction without requiring manual population filters.
