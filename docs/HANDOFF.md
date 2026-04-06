# Session Handoff

**Last updated:** 2026-04-06 (post Batch 1 + Batch 2 Python technique ports)

This document captures current project state for agent session continuity. Read this at the start of a new session. Update it before compaction or at natural milestones.

## Current State

### What's built

`middens` is a usable end-to-end CLI tool for analyzing AI agent session logs.

```bash
middens analyze ~/.claude/projects/ -o results/       # full battery
middens analyze path/ --split                          # stratified by session type
middens analyze path/ --techniques markov,entropy      # subset
middens parse file.jsonl                               # single file debug
middens freeze corpus/ -o manifest.json                # corpus snapshot
middens list-techniques                                # show 6 registered techniques
```

### Implementation status

| Component | Status | Notes |
|-----------|--------|-------|
| Parsers | Done | Claude Code, Codex, OpenClaw (Gemini stub) |
| Classifiers | Done | Message (5-priority) + session type (interactive/subagent) |
| Corpus discovery | Done | Recursive scan, symlink following, auto-discover |
| Techniques (Rust) | Done (6) | markov, entropy, diversity, burstiness, correction-rate, thinking-divergence |
| Output engine | Done | Markdown (YAML frontmatter), JSON, ASCII (sparklines, bars, tables) |
| Analyze pipeline | Done | discover → parse → classify → techniques → output |
| `--split` | Done | Automatic interactive/subagent stratification |
| Python bridge | Done | UvManager + PythonTechnique wrapper (merged PR #3) |
| Python techniques | 8/13 | Batch 1 + 2 done. Batch 3 remaining (5 techniques) |
| `fingerprint` | Stub | Environment extraction not implemented |
| `report` | Stub | Cross-technique synthesis not implemented |
| Parquet/Vega-Lite | Not started | Extended output formats (todos/remaining-cli.md) |

### Python techniques status

**Batch 1 (merged):** hsmm, information_foraging, granger_causality, survival_analysis
**Batch 2 (merged):** process_mining, prefixspan_mining, smith_waterman, tpattern_detection
**Batch 3 (pending):** lag_sequential, spc_control_charts, ncd_clustering, ena_analysis, convention_epidemiology

NLSpecs at `middens/docs/nlspecs/2026-04-05-python-techniques-batch{1,2}-nlspec.md`. Use the same shared contract for Batch 3:
- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout (with `name`, `summary`, `findings`, `tables`, `figures`)
- `tool_calls[].input` is a dict (not string) — extract `path` key
- Roles are `User`/`Assistant` (PascalCase), classifications like `HumanCorrection`/`Unclassified`
- Tables `rows` must be `List[List[Value]]` not `List[Dict]` (serde mismatch)
- Always sanitize NaN/Infinity before json.dumps
- Stderr output on file errors, exit 1
- Empty/insufficient sessions: return valid TechniqueResult with summary, NOT error exit

### Branches

| Branch | Status |
|--------|--------|
| `main` | Current — all phases through Python bridge merged |

### Test suite

240 Cucumber/Gherkin scenarios, 1242 steps. Runner at `middens/tests/cucumber.rs`. Feature files organized by domain under `middens/tests/features/`. Python technique tests at `tests/features/techniques/python_batch1.feature` (covers Batches 1+2).

## Process

### Adversarial development (foundry-style)

Non-trivial features use red/green adversarial process:
1. Write NLSpec (Why/What/How/Done) — review before proceeding
2. Red team (Codex or Gemini 3.1 Pro) writes Cucumber tests from DoD only
3. Green team (different model: Kimi K2.5 via OpenCode bash heredoc, or Gemini) implements from How section only
4. Run tests, send PASS/FAIL only to green team (no assertion text or error messages)
5. When tests fail: classify (contract gap / red bug / green bug / improvement), route to correct team
6. **Never adapt tests to match unauthorized API deviations** — amend the spec or reject

**Model selection (validated by Batches 1+2):**
- Red team: Gemini 3.1 Pro Preview (quality default — fewer iterations than 2.5 Pro)
- Green team: Kimi K2.5 via OpenCode (use bash heredoc, NOT write tool — write tool corrupts JSON payloads)
- Dispatch one file per Kimi invocation (large payloads break the tool layer)
- Codex available but quota-limited

Process learnings documented in foundry: `~/Projects/lightless-labs/foundry/docs/solutions/` and locally in `docs/solutions/best-practices/` and `docs/solutions/workflow-issues/`.

### Delegation

- Codex (GPT-5.4): `timeout: 600000` on Bash calls, use `-o` flag not pipes (quota-limited)
- Gemini: `-y -s false` for yolo + file writes. Use `gemini-3.1-pro-preview` for quality work, `gemini-2.5-pro` only for reasoning-heavy tasks
- OpenCode (Kimi): `kimi-for-coding/k2p5` model ID, `--format json` required, use bash heredoc for file writes (write tool broken). Dispatch one file per invocation
- Match tool to task: CLI tools for self-contained units, subagents for crate-context work

### Todos

Individual files in `todos/` following phil-connors pattern (YAML frontmatter with status, priority, issue_id, tags, source). When triaging PR review comments, reply with the todo file link.

Key todo files:
- `todos/python-bridge.md` — Phase 4: 13 Python technique ports
- `todos/remaining-cli.md` — fingerprint, report, Parquet, Vega-Lite, config
- `todos/research-reruns.md` — Granger, survival, process mining with corrected classifier
- `todos/023-pending-p1-peer-review-methodology-findings.md` — unaddressed research methodology issues
- `todos/009-026` — individual P2/P3 code review fixes

## What to do first in a new session

1. Read this file + `CLAUDE.md` + memory at `~/.claude/projects/-Users-thomas-Projects-lightless-labs-third-thoughts/memory/MEMORY.md`
2. Check for open PRs and review comments
3. Ask the user what they want to work on

## Before compaction / session end

1. Update this file with any new state changes
2. Commit if there are uncommitted changes
3. Update memory files if learnings were captured
