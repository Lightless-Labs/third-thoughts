# Account for `redact-thinking-2026-02-12` Beta Header

**Created:** 2026-04-06
**Status:** **DONE 2026-04-06 (PR #7 — `feat/thinking-visibility-stratification`)**
**Priority:** was P1
**Completed:** 2026-04-06
**Outcome:** Implemented as `Session::thinking_visibility` field with parser heuristic + `thinking-divergence` guard. **85.5% figure superseded by 100% on visible-only sessions (N=828, 4,819 risk tokens, 209 paired messages)**. Full write-up at `docs/solutions/methodology/redact-thinking-stratification-20260406.md`. Open question documented in PR #7 description: whether the CLAUDE.md Key Findings table should update in that PR or a follow-up.
**Source:** Anthropic comment on https://github.com/anthropics/claude-code/issues/42796#issuecomment-4194007103

## The insight

The `redact-thinking-2026-02-12` beta header is **UI-only**. From the Anthropic engineer:

> This beta header hides thinking from the UI, since most people don't look at it. It **does not** impact thinking itself, nor does it impact thinking budgets or the way extended reasoning works under the hood. It is a UI-only change.
>
> Under the hood, by setting this header we avoid needing thinking summaries, which reduces latency. You can opt out of it with `showThinkingSummaries: true` in your settings.json.
>
> If you are analyzing locally stored transcripts, you wouldn't see raw thinking stored when this header is set, which is likely influencing the analysis.

**Therefore:** any technique that measures thinking by counting `thinking` blocks in transcripts is **measuring transcript presence, not actual thinking**. Sessions where the header was set will look like "no thinking" but thinking was fully active.

## What this affects

- **`thinking-divergence` technique** (Rust) — directly affected. Its core metric (suppression rate, divergence ratio) is computed from the presence and length of thinking blocks in transcripts. Post-Feb-12 sessions with the header set will inflate the apparent suppression rate.
- **HSMM** — the behavioural-state model uses tool sequences, not thinking blocks. Probably unaffected, but verify.
- **Survival analysis** — depends on what the time-to-event is. If it's "time to first correction" the thinking block count is irrelevant. Verify.
- **The 85.5% risk-suppression headline finding** — needs re-checking. The retracted thinking-block-prevents-corrections finding (HANDOFF: "Thinking blocks prevent corrections — RETRACTED") may have been a header artifact, not a population artifact, or both. Re-examine.
- **GH#42796 replication** — already addressed in `~/claude-reasoning-performance-counter-analysis/report.md`. Adversarial counter-analysis already showed C2 (redaction rollout) and C3 (Write doubled) don't survive proper weighting. But the corpus composition anomaly is still the dominant story.

## What needs to happen

- [ ] **Detect the header in session metadata.** Determine where (if anywhere) the beta header is recorded in `~/.claude/projects/*.jsonl`. If it isn't recorded per-message, it may need to be inferred from `cwd` + session start time + a settings.json snapshot of `showThinkingSummaries`. Check the parser (`middens/src/parser/claude_code.rs`) to see what's currently captured.
- [ ] **If the header is not recorded in transcripts**, document this and consider whether the *absence* of any thinking block in a session can be used as a proxy. This is risky — pre-Feb-12 sessions could also lack thinking if the model didn't choose to reason. Need a temporal cutoff or a stronger signal.
- [ ] **Add a session-level flag** `thinking_visibility: visible | redacted | unknown` to the `Session` struct in `middens/src/session/mod.rs`. Compute it during parsing.
- [ ] **Update `thinking-divergence`** to (a) emit a `thinking_visibility` breakdown in its findings, (b) compute suppression rate ONLY on `visible` sessions, and (c) refuse to mix populations without an explicit flag.
- [ ] **Add a stratification gate to the pipeline** — when `thinking-divergence` is selected and the corpus contains both `visible` and `redacted` sessions, print a warning at the start of the run.
- [ ] **Re-run the 4 replications** of the 85.5% risk-suppression finding on `visible`-only sessions. If the number changes materially, downgrade or retract.
- [ ] **Note in `docs/methods-catalog.md`** under the thinking-divergence section that the technique requires `thinking_visibility=visible` to be meaningful.
- [ ] **Note in `docs/HANDOFF.md`** Key Findings table — annotate the 85.5% row as "pending re-validation under header stratification".
- [ ] Consider whether Anthropic exposes the header status at any API surface that we could log going forward (eg via `showThinkingSummaries` in settings.json snapshots).

## Adversarial process

This is a methodology change, not a feature. No red/green split needed. The work is:

1. Parser-level investigation (does the JSONL even contain header info?)
2. Session-struct enrichment (small Rust change, TDD via cucumber)
3. Technique-level guard (small Rust change in `thinking_divergence.rs`)
4. Re-running the 4 replications and writing up the result in `docs/solutions/methodology/`

**Critical:** if a re-run shows the 85.5% finding is partly an artifact, the report needs an update AND a `docs/solutions/methodology/redact-thinking-header-confound-2026-04-XX.md` writeup so this lesson doesn't get forgotten. This is exactly the same shape as the population-contamination retraction (`docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md`) — both are findings that dissolved under proper stratification.

## Open question for the user

Do you want to (a) bake the header detection into the parser as a hard requirement before any thinking analysis runs, or (b) leave thinking-divergence as-is and add a big WARNING banner in its output? Option (a) is more correct; option (b) is faster and lets distribution proceed while methodology catches up.
