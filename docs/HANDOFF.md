# Session Handoff

**Last updated:** 2026-04-04 (post Python bridge merge)

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
| Python techniques | Not started | 13 techniques to port (todos/python-bridge.md) |
| `fingerprint` | Stub | Environment extraction not implemented |
| `report` | Stub | Cross-technique synthesis not implemented |
| Parquet/Vega-Lite | Not started | Extended output formats (todos/remaining-cli.md) |

### Branches

| Branch | Status |
|--------|--------|
| `main` | Current — all phases through Python bridge merged |

### Test suite

205 Cucumber/Gherkin scenarios, 987 steps. Runner at `middens/tests/cucumber.rs`. Feature files organized by domain under `middens/tests/features/`.

## Process

### Adversarial development (foundry-style)

Non-trivial features use red/green adversarial process:
1. Write NLSpec (Why/What/How/Done) — review before proceeding
2. Red team (Codex or Gemini) writes Cucumber tests from DoD only
3. Green team (different model) implements from How section only
4. When tests fail: classify (contract gap / red bug / green bug / improvement), route to correct team
5. **Never adapt tests to match unauthorized API deviations** — amend the spec or reject

Process learnings documented in foundry: `~/Projects/lightless-labs/foundry/docs/solutions/`

### Delegation

- Codex (GPT-5.4): `timeout: 600000` on Bash calls, use `-o` flag not pipes
- Gemini: `-y -s false` for yolo + file writes
- OpenCode (GLM/Minimax/Kimi): can be very slow (5-15 min), use background dispatch
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
