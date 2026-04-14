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
  src/output/               # Legacy renderers: Markdown, JSON, ASCII (pre-triad)
  src/view/                 # View renderers: Jupyter notebook (post-triad)
  src/storage/              # Parquet writer, manifest model, PII validation, XDG discovery
  src/commands/             # interpret + export command implementations
  src/pipeline.rs           # analyze pipeline orchestration (writes storage + legacy output)
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

**Risk suppression is 100% on visible-thinking sessions.** Across 209 paired thinking/text messages in 828 visible-thinking English sessions (4,819 risk-token observations), every risk token in the thinking block is absent from the paired user-facing text. The earlier "85.5%" headline was a mixed-corpus artifact — redacted sessions trivially scored 0% and dragged the per-session mean down. See `docs/solutions/methodology/redact-thinking-stratification-20260406.md`.

## Key Findings

| Finding | Status | Evidence |
|---------|--------|----------|
| 99.99% risk suppression on visible-thinking sessions | **Strengthened** (2026-04-14 full-corpus run) | `language=en AND thinking_visibility=Visible`. N=4,518 sessions, 31,679 risk tokens, 2 leaks. Prior provisional (PR #7): N=828, 4,819 tokens. `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md` |
| 85.5% risk suppression on mixed corpus | **SUPERSEDED** (PR #7) | Mixed-corpus artifact — redacted sessions trivially scored 0% and dragged the per-session mean down. The phenomenon is unchanged; only the reported percentage moves. |
| HSMM pre-failure state (24.6x lift) | **Provisional — magnitude unconfirmed** (2026-04-14 run: 2.15x) | Direction replicates; 24.6x likely a Boucle contamination artifact. Needs re-run with W10–W12 excluded. `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md` |
| MVT violated (agents under-explore) | Robust | `experiments/full-corpus/information-foraging.md` |
| Thinking blocks prevent corrections | **RETRACTED** (did not survive population split) | `experiments/interactive/survival-results.json` |
| Session degradation (agents get worse) | Holds on interactive only | `experiments/interactive/survival_analysis.txt` |
| W10–W12 Boucle contamination in interactive bucket | **Confirmed** (PR #6) | 1,820 of 1,826 sessions carry the `queue-operation` marker; 100% have zero tool calls. `docs/solutions/methodology/corpus-composition-anomaly-w10-w12-investigation-20260406.md` |

**Compound scoping rule:** every future headline finding on thinking or text behaviour should be scoped on at least four axes: `session_type ∈ {Interactive, Subagent, Autonomous}`, `thinking_visibility ∈ {Visible, Redacted, Unknown}`, `language ∈ {en, other}`, and a temporal window. A finding that doesn't survive all four is not a finding.

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
| Minimax M2.7 | `minimax-coding-plan/MiniMax-M2.7` | Faster than GLM, but architectural bugs |

- **Kimi has tool use** through OpenCode's tool layer. Use `--format json` to get NDJSON output — without it, ANSI escape codes corrupt code extraction. Validated in A²D project (skunkworks/a2d).
- NDJSON output format: `{"type":"text","part":{"text":"..."}}` — parse by filtering for `type == "text"` and extracting `/part/text`.
- **Kimi write tool is broken** — JSON serialization corrupts tool call payloads (tokenizer tokens leak into JSON). Workaround: tell Kimi to write files via bash heredoc (`cat > file << 'EOF'`) instead of the write/edit tool. One file per invocation.
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

- **Prose tone: light and self-deprecating, never pompous.** When writing READMEs, project blurbs, commit messages, or any user-facing copy, prefer the honest/wry register over earnest research-speak. Example: "studying AI agent behavior at scale through multi-disciplinary corpus analysis (basically, throwing stuff at the wall and seeing what sticks)" is the voice we want. Technical precision in methodology docs is still fine — this rule is about framing and register, not rigor.
- **Fail early, fail fast, fail clearly.** Never guess user intent. When CLI / API / function input is ambiguous — a flag whose value doesn't match the expected structure, a default that could plausibly resolve multiple ways, a resource in an unclear state — reject it loudly with a clear message. Do not silently coerce, fall back, or pick an interpretation. Error messages should say (a) what was wrong, (b) what the expected form was, (c) a concrete example of correct input. Rationale: silent fallbacks hide bugs, confuse users when the guess turns out wrong, and make testing harder because the failure mode becomes "correct output for the wrong question". Applies to the middens CLI, scripts, library APIs, anywhere code accepts external input. (Full version in parent `CLAUDE.md`; this project inherits it.)
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
