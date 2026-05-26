---
date: 2026-04-02
topic: middens-split-stratification
status: draft
updated: 2026-05-26 — Autonomous stratum added; Unknown sessions are excluded from all strata.
---

# Middens --split Automatic Stratification

## 1. Why
The corpus contains interactive (human-in-the-loop), subagent (delegated sidechain/tool-result), and autonomous (agent loop, no observed human participation) sessions. Mixing them produces contaminated statistics (p=10⁻⁴² → p=0.40). `--split` runs the technique battery separately on each population.

## 2. What
When `--split` is passed, the pipeline partitions sessions by `session.session_type` (Interactive, Subagent, Autonomous, Unknown) and runs techniques on each known partition separately, writing results to `{output_dir}/interactive/`, `{output_dir}/subagent/`, and `{output_dir}/autonomous/` subdirectories. Unknown sessions are excluded from all strata to avoid contaminating any population.

## 3. How
In `src/pipeline.rs`, when `config.split` is true:
1. After parsing, partition sessions into interactive, subagent, autonomous, and unknown vectors
2. Run the technique loop three times: once each for interactive, subagent, and autonomous
3. Write results to `{output_dir}/interactive/`, `{output_dir}/subagent/`, and `{output_dir}/autonomous/`
4. Report counts for each known population in the summary

Add `split: bool` to `PipelineConfig`. Wire from `Commands::Analyze { split }` in main.rs.

## 6. Definition of Done
- [ ] `--split` flag partitions sessions by SessionType
- [ ] Interactive results written to `{output_dir}/interactive/`
- [ ] Subagent results written to `{output_dir}/subagent/`
- [ ] Autonomous results written to `{output_dir}/autonomous/`
- [ ] Unknown sessions excluded from all populations
- [ ] Without `--split`, behavior unchanged (flat output directory)
- [ ] Summary reports per-population counts
