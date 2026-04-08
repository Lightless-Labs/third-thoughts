---
title: "Corpus composition anomaly W10–W12 — investigation findings"
module: third-thoughts
date: 2026-04-06
problem_type: methodology
component: corpus-stratification
severity: high
status: investigated
tags:
  - corpus-integrity
  - population-stratification
  - temporal-analysis
---

## Headline Finding

**The W10–W12 "interactive" corpus is effectively fully contaminated with Boucle autonomous agent loop iterations.** Of the 1,826 sessions in these weeks, **1,820 (99.7%) carry the `queue-operation` type marker**, and **all 1,826 (100%) have zero tool calls** — the definitive smoking gun. The 6 sessions without the `queue-operation` marker (5 in W10, 1 in W11, 0 in W12 — see the Automation Fingerprints table) still exhibit zero tool calls and Boucle-consistent message shapes. The 45× session count explosion (W09 27 → W11 1,221) is **NOT model regression**, but wholesale misclassification of autonomous agent sessions into the interactive bucket. **Temporal findings after W09 must be retracted or stratified by session type.**

> The original HANDOFF framing described a "tool-rate collapse from 572 → 8.9 tools/session" based on the pre-investigation stratification summary. That figure is superseded by this investigation: within W10–W12 tools/session is actually **0.000**, not 8.9. The 8.9 number came from blending the contaminated W10–W12 bucket with a broader interactive sample; once W10–W12 is measured on its own, the true value is zero, which makes the model-regression framing mechanically impossible.

---

## Methodology

### Population

- **Corpus location:** `corpus-split/interactive/` (2,596 symlinked JSONL session files)
- **Target weeks:** W10, W11, W12 of ISO 2026 (2026-03-02 through 2026-03-22)
- **Sampling:** All sessions (n=1,826) with valid ISO 8601 timestamp in first message

### Measurements per session

1. **Message structure:**
   - Total lines in JSONL (messages and metadata)
   - Count by type field (user, assistant, queue-operation, last-prompt, etc.)
   - Count of user-role messages only

2. **Tool call detection:**
   - Search message.content[] for type: "tool_use" blocks
   - Tally per session and aggregate

3. **Automation fingerprints:**
   - `queue-operation` type (indicates agent loop iteration, NOT interactive)
   - `<run_context>` XML tag (agent state injection)
   - Mentions of "Boucle" or "autonomous agent" in content
   - Zero tool calls (defines empty session)

4. **Project metadata:**
   - Extract project name from cwd field when available

---

## Distribution Results

### Session counts

| Week | Sessions | Total Messages | Avg Msgs/Session | Median | Range |
|------|----------|----------------|-----------------|--------|-------|
| W09 (baseline) | 27 | — | — | — | — |
| W10  | 60       | 8,078          | 134.6           | 6      | 2–1,454 |
| W11  | 1,221    | 115,715        | 94.8            | 6      | 2–57,975 |
| W12  | 545      | 5,003          | 9.2             | 5      | 5–2,126 |
| **W10–W12 Total** | **1,826** | **128,796** | **70.5** | **6** | **2–57,975** |

The W09 → W11 jump is the 45× explosion called out in the headline (27 → 1,221).

### Tool call distribution (the smoking gun)

| Week | Total Tools | Avg Tools/Session | Zero-Tool Sessions | % Zero-Tool |
|------|-------------|-------------------|--------------------|-------------|
| W10  | 0           | 0.000             | 60                 | 100.0%      |
| W11  | 0           | 0.000             | 1,221              | 100.0%      |
| W12  | 0           | 0.000             | 545                | 100.0%      |

**Conclusion:** W10–W12 interactive sessions have exactly **0 tool calls across 1,826 sessions**. This is impossible for real interactive sessions with 8–114 tools/session baseline. The corpus is contaminated.

### Message length histograms

```
W10: 60 sessions
  0-0       :     0 (  0.0%)
  1-4       :     5 (  8.3%) ████
  5-19      :    41 ( 68.3%) ██████████████████████████████████
  20-49     :     0 (  0.0%)
  50-199    :     1 (  1.7%)
  200+      :    13 ( 21.7%) ██████████

W11: 1,221 sessions
  0-0       :     0 (  0.0%)
  1-4       :    25 (  2.0%) █
  5-19      :  1,092 ( 89.4%) ████████████████████████████████████████████
  20-49     :    17 (  1.4%)
  50-199    :    23 (  1.9%)
  200+      :    64 (  5.2%) ██

W12: 545 sessions
  0-0       :     0 (  0.0%)
  1-4       :     0 (  0.0%)
  5-19      :   544 ( 99.8%) █████████████████████████████████████████████████
  20-49     :     0 (  0.0%)
  50-199    :     0 (  0.0%)
  200+      :     1 (  0.2%)
```

**Interpretation:**
- **W11:** 89.4% have 5–19 messages (mode 6). Boucle loop iteration footprint.
- **W12:** 99.8% have 5–19 messages. Automated/repetitive content.

---

## Automation Fingerprints

### Queue-operation type (definitive marker)

The type: "queue-operation" field indicates agent loop iteration, not interactive session.

| Week | Queue-Operation Count | % of Sessions |
|------|----------------------|----------------|
| W10  | 55                   | 91.7%          |
| W11  | 1,220                | **99.9%**      |
| W12  | 545                  | **100.0%**     |

### Boucle semantic markers

| Week | Boucle Mentions | % Mentions | `<run_context>` Tag | % Tag |
|------|-----------------|---|-------------------|---|
| W10  | 51              | 85.0% | 0               | 0.0% |
| W11  | 643             | 52.7% | 514             | 42.1% |
| W12  | 483             | 88.6% | 66              | 12.1% |

**Interpretation:** 52.7%–88.6% explicitly mention Boucle. These are agent loop state dumps, not human-interactive prompts.

---

## Correction_classifier Verification

Sample re-classification (100 random W11 sessions):

| Marker | Count | % |
|--------|-------|---|
| queue-operation type | 100 | 100.0% |
| `<run_context>` tag present | 39 | 39.0% |
| Boucle mention | 56 | 56.0% |
| Tool use calls | 0 | 0.0% |

---

## Root Cause

The corpus-split/ stratification does not filter out queue-operation type sessions, which are Boucle agent infrastructure (not interactive). These sessions have human-like message alternation but zero tool calls — the key distinguishing feature.

### Evidence

1. **100% zero tool calls** across all 1,826 W10–W12 "interactive" sessions
2. **99.7% `queue-operation` type** across W10–W12 (1,820 of 1,826); **99.9%+ in W11 and W12** individually
3. **52.7%–88.6% Boucle mentions**
4. **89.4%–99.8% sessions with 5–19 messages** (automated loop footprint)
5. **45× session explosion with tools/session collapsing to exactly 0** (population shift, not model regression)

---

## Recommendation

**Option (A): Retract temporal findings on W10–W12 interactive corpus.**

The interactive bucket is unsuitable for model behavior analysis after W09 due to Boucle infrastructure contamination. All temporal findings spanning W10–W12 must be either:
1. Re-run with W10–W12 excluded, OR
2. Published with explicit caveat: "W10–W12 interactive population contaminated with ≥99.7% agent infrastructure sessions; findings on this subset are not reliable."

**Option (B): Apply session-type filter and re-stratify**

Promote `queue-operation` type to a first-class `Autonomous` session stratum (see `todos/autonomous-session-stratum.md`). After filtering by `queue-operation` alone, W10 would collapse from 60 → 5, W11 from 1,221 → 1, and W12 from 545 → 0 remaining sessions. **However, those 6 leftover sessions still have zero tool calls and Boucle-consistent message shapes** (see Headline Finding). They should therefore be classified as `Autonomous` as well — via a secondary rule such as "zero tool calls + Boucle markers" — rather than re-admitted to the interactive bucket. The net effect is zero true interactive signal in this window.

---

## Conclusion

The W10–W12 anomaly is **definitively a stratification error**: 1,820 of 1,826 "interactive" sessions in this window carry the `queue-operation` marker, and all 1,826 have exactly zero tool calls — explicit agent loop footprints, not interactive Claude Code usage. **All temporal findings after W09 on the interactive bucket are invalid and must be retracted or re-run under the new 3-way stratification (Interactive / Subagent / Autonomous — see `todos/autonomous-session-stratum.md`).**

