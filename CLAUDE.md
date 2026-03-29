# Third Thoughts

Lightless Labs research project studying AI agent behavior at scale through multi-disciplinary corpus analysis.

Named after Tiffany Aching's concept from Discworld: first thoughts (agents thinking), second thoughts (agents analyzing their thinking), third thoughts (this project analyzing *that*).

## Directory Structure

```
middens/                    # Rust CLI tool (Phase 1 complete, 49 tests)
  src/parser/               # Pluggable parsers: Claude Code, Codex, OpenClaw, Gemini (stub)
  src/classifier/           # Message + session type classification
  src/corpus/               # Discovery, indexing, manifests
  src/techniques/           # Analytical technique trait (stubs)
  python/                   # Python scripts for complex techniques (Phase 4)
corpus/                     # Raw session logs (third-thoughts subset)
corpus-full/                # Unified corpus via symlinks (~4.8 GB, 7,909 sessions)
corpus-split/               # Pre-split: interactive/ (2,594) + subagent/ (5,348)
corpus-frozen/              # Reproducibility manifest (7,990 files)
data/                       # Derived data: labeled-messages.json, validation results
scripts/                    # 26 Python analysis scripts (the analytical battery)
experiments/                # Analysis outputs organized by run context
  full-corpus/              # Full 4.8 GB corpus results (23 techniques)
  interactive/              # Interactive-only stratified results
  subagent/                 # Subagent-only stratified results
docs/
  methods-catalog.md        # 20 method families, 80+ references
  reports/                  # Research reports + PDFs
  reviews/                  # Multi-model peer reviews
  brainstorms/              # Requirements docs
  plans/                    # Implementation plans
  solutions/                # Institutional knowledge (learnings)
todos/                      # Outstanding work items
```

## Critical Methodological Notes

**ALWAYS stratify by session type.** The corpus contains 2,594 interactive and 5,348 subagent sessions. Mixing them produced inflated statistics (p=10⁻⁴² → p=0.40 on the same finding). See `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md`.

**Use the validated correction classifier.** The regex-based approach fails on subagent sessions (90% false positive rate). The structural classifier at `scripts/correction_classifier.py` achieves 98% accuracy by checking for tool_result content blocks before applying lexical patterns. See `data/labeled-messages.json` for the labeled dataset.

**Risk suppression is 85.5%.** This replicated identically across 4 independent analyses. It is the most robust finding in the corpus.

## Key Findings

| Finding | Status | Evidence |
|---------|--------|----------|
| 85.5% risk suppression | **Robust** (4 replications) | `experiments/*/010_thinking_block_divergence.txt` |
| HSMM pre-failure state (24.6x lift) | Robust (mixed corpus) | `experiments/full-corpus/hsmm_behavioral_states.txt` |
| MVT violated (agents under-explore) | Robust | `experiments/full-corpus/information-foraging.md` |
| Thinking blocks prevent corrections | **RETRACTED** (did not survive population split) | `experiments/interactive/survival-results.json` |
| Session degradation (agents get worse) | Holds on interactive only | `experiments/interactive/survival_analysis.txt` |

## Middens CLI

The `middens` CLI tool at `middens/` is the productized version of this research. Phase 1 (parsers + classifiers + discovery) is complete. See `docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md` for the full plan.

Build: `cd middens && cargo build --release`
Test: `cd middens && cargo test`

## Multi-Model Analysis

When running cross-model evaluations:
- Codex CLI: `codex exec --skip-git-repo-check -c 'sandbox_permissions=["disk-full-read-access","disk-write-access"]' "prompt"`
- Gemini CLI: `gemini -y -s false --prompt "prompt"` (yolo mode + no sandbox for file writes)
- Claude subagents: `Agent` tool with `mode: bypassPermissions`

See `docs/solutions/methodology/multi-model-refinery-synthesis-20260320.md` for the full process.

## Conventions

- Follow Lightless Labs conventions from parent `CLAUDE.md` (Rust, Bazel aspirational, TDD, atomic commits)
- Analysis outputs go to `experiments/{context}/` (e.g., `full-corpus/`, `interactive/`, `subagent/`)
- All techniques documented in `docs/methods-catalog.md` with academic references
- Findings that don't survive stratification must be retracted or downgraded in reports
