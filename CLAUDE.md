# Third Thoughts

Lightless Labs research project studying AI agent behavior at scale through multi-disciplinary corpus analysis.

Named after Tiffany Aching's concept from Discworld: first thoughts (agents thinking), second thoughts (agents analyzing their thinking), third thoughts (this project analyzing *that*).

## Session Continuity

**Read `docs/HANDOFF.md` at the start of every session.** It has current implementation status, open PRs, branch state, and what to do first. Update it before compaction or at natural milestones.

## Directory Structure

```
middens/                    # Rust CLI tool — usable end-to-end
  src/parser/               # Pluggable parsers: Claude Code, Codex, OpenClaw, Gemini (stub)
  src/classifier/           # Message + session type classification
  src/corpus/               # Discovery, indexing, manifests
  src/techniques/           # 6 Rust-native analytical techniques
  src/output/               # Markdown, JSON, ASCII renderers
  src/pipeline.rs           # analyze pipeline orchestration
  src/bridge/               # Python bridge (UvManager, PythonTechnique)
  python/techniques/        # Python technique scripts (echo.py test fixture)
  tests/features/           # Cucumber/Gherkin .feature files
  tests/steps/              # Step definitions
corpus/                     # Raw session logs (gitignored — private data)
corpus-full/                # Unified corpus via symlinks (gitignored)
corpus-split/               # Pre-split: interactive/ + subagent/ (gitignored)
corpus-frozen/              # Reproducibility manifest (gitignored)
scripts/                    # 26 Python analysis scripts (the analytical battery)
experiments/                # Analysis outputs (gitignored — contain real usernames)
docs/
  HANDOFF.md                # Current state for session continuity
  methods-catalog.md        # 20 method families, 80+ references
  nlspecs/                  # Natural Language Specifications (Why/What/How/Done)
  reports/                  # Research reports
  reviews/                  # Multi-model peer reviews
  brainstorms/              # Requirements docs
  plans/                    # Implementation plans
  solutions/                # Institutional knowledge (learnings)
todos/                      # Individual todo files (phil-connors pattern)
```

## Critical Methodological Notes

**ALWAYS stratify by session type.** The corpus contains 2,594 interactive and 5,348 subagent sessions. Mixing them produced inflated statistics (p=10⁻⁴² → p=0.40 on the same finding). See `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md`.

**Use the validated correction classifier.** The regex-based approach fails on subagent sessions (90% false positive rate). The structural classifier at `scripts/correction_classifier.py` achieves 98% accuracy by checking for tool_result content blocks before applying lexical patterns.

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

Build: `cd middens && cargo build --release`
Test: `cd middens && cargo test`

See `docs/HANDOFF.md` for current implementation status and `docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md` for the original plan.

## Multi-Model Analysis

When running cross-model evaluations:
- Codex CLI: `codex exec --skip-git-repo-check --full-auto "prompt"` (always set `timeout: 600000` on Bash calls — default 120s auto-backgrounds, and piped output doesn't flush, so 10 min of compute is lost silently. Use `-o output.md` not pipes.)
- Gemini CLI: `gemini -y -s false --prompt "prompt"` (yolo mode + no sandbox for file writes)
- OpenCode CLI: `opencode run --model provider/model "prompt"` (can be very slow — 5-15 min)
- Claude subagents: `Agent` tool with `mode: bypassPermissions`

### OpenCode model IDs and flags

| Model | ID | Notes |
|-------|-----|-------|
| Kimi K2.5 | `kimi-for-coding/k2p5` | NOT `kimi/kimi-k2.5` — old ID fails silently |
| GLM 5.1 | `zai-coding-plan/glm-5.1` | Slow (5-10 min), minimal output |
| Minimax M2.7 | `minimax/minimax-m2.7` | Faster than GLM, but architectural bugs |

- **Kimi has tool use** through OpenCode's tool layer. Use `--format json` to get NDJSON output — without it, ANSI escape codes corrupt code extraction. Validated in A²D project (skunkworks/a2d).
- NDJSON output format: `{"type":"text","part":{"text":"..."}}` — parse by filtering for `type == "text"` and extracting `/part/text`.
- Background dispatch: `opencode run --model provider/model --format json "prompt" > log.log 2>&1 &`

### Automated PR review workflow

This repo has Codex, Copilot, Gemini, and CodeRabbit automated reviews. When addressing review feedback:
1. Fetch all comments: `gh api repos/.../pulls/{n}/comments --paginate`
2. Triage by priority (P1 > P2 > cosmetic). Group converging comments from different reviewers.
3. Batch fixes by file, atomic commit per round with detailed message listing what was addressed.
4. Reply to every comment via `gh api repos/.../pulls/{n}/comments/{id}/replies -f body="..."`
5. Push and wait for re-reviews — reviewers trigger on each push.
6. CodeRabbit auto-pauses after rapid commits (`@coderabbitai resume` to re-enable).
7. Iterate until no new P1/P2 findings.

## Conventions

- Follow Lightless Labs conventions from parent `CLAUDE.md` (Rust, Bazel aspirational, TDD, atomic commits)
- Analysis outputs go to `experiments/{context}/` (gitignored — contain private data)
- All techniques documented in `docs/methods-catalog.md` with academic references
- Findings that don't survive stratification must be retracted or downgraded in reports
- Todos as individual files in `todos/` with YAML frontmatter (status, priority, issue_id, tags, source)
- Corpus data (corpus*/, experiments/, data/labeled-messages.json) must NEVER be committed — .gitignore handles this but be aware
- Non-trivial features use adversarial process (full methodology in foundry docs at `~/Projects/lightless-labs/foundry/docs/solutions/`):
  1. Write NLSpec → review → red team writes tests from DoD only → green team implements from How only
  2. **Information barrier:** orchestrator must NOT fix step definitions or implementation directly — route filtered feedback to the correct team
  3. When tests fail: diagnose whether spec was unclear (amend NLSpec) or implementation wrong (route PASS/FAIL to green WITHOUT showing test code)
  4. Use `/codex-cli`, `/gemini-cli`, `/opencode-cli` skills for red/green dispatch — enforces context isolation naturally
  5. Match tool to task: CLI tools for self-contained units, subagents for crate-context work, inline for small surgical fixes
