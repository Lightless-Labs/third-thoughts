---
date: 2026-03-20
problem_type: methodology_error
severity: critical
symptoms:
  - "Survival analysis shows HR=0.204 (p=10⁻⁴²) on mixed corpus but HR=0.663 (p=0.40, NS) on interactive-only"
  - "Hazard trend reverses direction when subagent sessions are included vs excluded"
  - "Correction rate inflated to 90% in subagent sessions where tool results are misclassified as corrections"
  - "Monoculture rate jumps from 3.7% to 46% when subagent sessions are included"
tags: [population-split, subagent, interactive, contamination, stratification, correction-classifier]
---

# Population Contamination: Mixing Interactive and Subagent Sessions Produces Misleading Aggregates

## Problem

The 4.8 GB corpus contains 2,594 interactive sessions (human-in-the-loop) and 5,348 subagent sessions (autonomous tool-use loops). Analyzing them together produced spectacular but false statistical results.

The smoking gun: a Cox Proportional Hazards model showed thinking blocks reduce correction hazard by 79.6% (HR=0.204, p=7×10⁻⁴²) on the mixed corpus. On interactive sessions alone: HR=0.663, p=0.40 — not significant. The entire finding was an artifact of mixing two fundamentally different populations.

## Root Cause

Regex-based correction classifiers match words like "fix", "error", "no" in message text. In interactive sessions, these correctly identify human corrections. In subagent sessions, "user" messages are actually tool result returns from the parent agent or system notifications. These frequently contain correction-pattern words ("error: no such file", "fix the path") despite being machine-generated, not human corrections.

Because subagents outnumber interactive sessions 2:1 and almost always trigger the correction classifier (90% "correction rate"), any analysis using correction as a variable is dominated by the subagent signal.

## Solution

1. **Always stratify by session type.** Report interactive and subagent results separately. Mixed-corpus results are only meaningful for metrics unaffected by the correction classifier.

2. **Use structural-first correction classification.** The validated classifier (98% accuracy) checks for tool_result content blocks BEFORE applying lexical patterns. This eliminates all false positives in subagent sessions. See `scripts/correction_classifier.py`.

3. **Classify session type using structural signals, not regex.** Check: path contains "subagent" directory component, presence of agentId field, isSidechain flag, absence of human-authored text content.

## Prevention

- Before running any analysis that uses "correction" as a variable, verify the correction classifier's false positive rate on the target population
- When reporting findings, always state: N interactive sessions, N subagent sessions, which population the finding was measured on
- Treat any finding with p < 10⁻¹⁰ with suspicion — it may indicate population confounding rather than a genuine effect

## Cross-References

- Full analysis: `docs/reports/third-thoughts-full-corpus-report.md` (Addendum)
- Correction classifier: `scripts/correction_classifier.py`
- Labeled dataset: `data/labeled-messages.json`
- Validation report: `experiments/correction-classifier-validation.md`
