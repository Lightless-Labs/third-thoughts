---
date: 2026-04-02
topic: middens-split-stratification
status: draft
---

# Middens --split Automatic Stratification

## 1. Why
The corpus contains interactive (human-in-the-loop) and subagent (automated) sessions. Mixing them produces contaminated statistics (p=10⁻⁴² → p=0.40). `--split` runs the technique battery separately on each population.

## 2. What
When `--split` is passed, the pipeline partitions sessions by `session.session_type` (Interactive, Subagent, Unknown) and runs techniques on each partition separately, writing results to `{output_dir}/interactive/` and `{output_dir}/subagent/` subdirectories. Unknown sessions are included in both runs.

## 3. How
In `src/pipeline.rs`, when `config.split` is true:
1. After parsing, partition sessions into interactive, subagent, and unknown vectors
2. Run the technique loop twice: once for interactive + unknown, once for subagent + unknown
3. Write results to `{output_dir}/interactive/` and `{output_dir}/subagent/`
4. Report counts for each population in the summary

Add `split: bool` to `PipelineConfig`. Wire from `Commands::Analyze { split }` in main.rs.

## 6. Definition of Done
- [ ] `--split` flag partitions sessions by SessionType
- [ ] Interactive results written to `{output_dir}/interactive/`
- [ ] Subagent results written to `{output_dir}/subagent/`
- [ ] Unknown sessions included in both populations
- [ ] Without `--split`, behavior unchanged (flat output directory)
- [ ] Summary reports per-population counts
