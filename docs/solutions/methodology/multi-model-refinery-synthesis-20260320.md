---
date: 2026-03-20
problem_type: process_pattern
severity: medium
symptoms:
  - "Need to validate findings across model families to avoid single-model bias"
  - "Want cross-evaluation where each model critiques the others' analysis"
  - "Need to distinguish 'best argued' from 'most agreed upon'"
tags: [refinery, multi-model, consensus, synthesis, claude, codex, gemini]
---

# Multi-Model Refinery Synthesis: Orchestrating Cross-Model Evaluation

## Pattern

When producing research reports or evaluating findings, run independent analyses across multiple model families, then have each model evaluate all reports. This produces findings that no single model would surface alone.

## Implementation (as executed in this session)

### Step 1: Independent Generation
Launch all three models in parallel, each reading the same source data:
```bash
# Claude subagent
Agent: "Read the data, write your independent report to report-claude.md"

# Codex CLI
codex exec --skip-git-repo-check -c 'sandbox_permissions=["disk-full-read-access","disk-write-access"]' "Read the data, write report to report-codex.md"

# Gemini CLI
gemini -y -s false --prompt "Read the data, write report to report-gemini.md"
```

### Step 2: Cross-Evaluation (R1 Synthesis)
Each model reads all three reports and scores them on: analytical depth, factual accuracy, novelty, actionability. Each identifies contradictions between reports and proposes the strongest composite.

### Step 3: Final Synthesis
Consolidate R1 feedback. Where reports contradict, adjudicate against raw evidence. The final report uses "Codex's factual skeleton + Claude's conceptual spine + Gemini's practitioner framing."

## Key Findings About the Process Itself

- **Codex (GPT-5.4) wins on factual accuracy.** It caught the unanimity overstatement, correctly distinguished answer-scoring from pattern-scoring, and introduced Borda-style rank aggregation.
- **Claude wins on analytical depth** but is verbose and repeats article claims without checking them.
- **Gemini contributes unique concepts** ("Scars without Wounds", consensus-as-hallucination-multiplier) but has the thinnest supporting analysis.
- **The refinery scores answers, not patterns.** It selects the best-argued synthesis, not a pure statistical aggregate. This distinction matters for interpretation.
- **Narrative drift risk:** The editorial refinery polished overstatements rather than correcting them. Once a clean narrative enters the loop, peer models reinforce it stylistically.

## Practical Notes

- Codex CLI needs `--skip-git-repo-check` when running outside a trusted directory
- Gemini CLI needs `-y` (yolo mode) and `-s false` (no sandbox) to write files
- Gemini often can't write to paths outside its workspace — use `cp` to move output afterward
- Codex sometimes outputs to stdout instead of writing files — capture with `sed` extraction
- All three parsers differ on timeout handling and file access patterns

## Cross-References

- Synthesis reports: `docs/agentic-engineering-sawdust-synthesis-r1-{claude,codex,gemini}.md`
- Final synthesis: `docs/agentic-engineering-sawdust-final-synthesis.md`
