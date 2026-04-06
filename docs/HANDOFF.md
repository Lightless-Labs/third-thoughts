# Session Handoff

**Last updated:** 2026-04-06 (Batch 3 Python techniques — all 13/13 ported)

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
| Python techniques | **13/13** | Batches 1 + 2 + 3 done. All registered dynamically in cucumber tests only — NOT wired into `all_techniques()` in `src/techniques/mod.rs` yet (pre-existing gap from Batch 1). |
| `fingerprint` | Stub, *superseded* | Reframed as a technique in `docs/design/output-contract.md` |
| `report` | Stub, *reshaped* | New contract `(run_id, format) → view file`. See `todos/output-contract.md` |
| Storage/view split | Designed, not implemented | `docs/design/output-contract.md`, `todos/output-contract.md` — next major work |
| Conclusions v1/v2 | Designed | `todos/conclusions-v{1-manual,2-synthesize}.md` |

### Python techniques status

**Batch 1 (merged):** hsmm, information_foraging, granger_causality, survival_analysis
**Batch 2 (merged):** process_mining, prefixspan_mining, smith_waterman, tpattern_detection
**Batch 3 (merged):** lag_sequential, spc_control_charts, ncd_clustering, ena_analysis, convention_epidemiology

NLSpecs at `middens/docs/nlspecs/2026-04-{05,06}-python-techniques-batch{1,2,3}-nlspec.md`. Shared contract:
- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout
- **Tables must be `{"name": ..., "columns": [...], "rows": [[...]]}`** — NOT `{"title", "headers", "rows"}`. This is a recurring spec gotcha; the Rust `DataTable` struct uses `name`+`columns`. Batch 3 lost a full round of rework to this.
- `tool_calls[].input` is a dict (not string) — extract keys like `input.get("path")`
- `tool_results[].tool_use_id` not `id` (Rust `ToolResult` uses `tool_use_id`)
- Roles are `User`/`Assistant` (PascalCase), classifications like `HumanCorrection`/`Unclassified`
- Rows are `List[List[Value]]` not `List[Dict]`, type-homogeneous per column
- Always sanitize NaN/Infinity before json.dumps
- Stderr output on file errors, exit 1
- Empty/insufficient sessions: return valid TechniqueResult with summary containing "insufficient", NOT error exit
- Summary substring assertions are case-insensitive but literal — if the spec says "mention 'lag sequential'" the actual summary must contain "lag sequential" (space, not hyphen)
- Test fixtures have `timestamp: None` — techniques that order by timestamp must fall back to array index ordering

### Branches

| Branch | Status |
|--------|--------|
| `main` | Current — all phases through Python bridge merged |

### Test suite

**261 Cucumber/Gherkin scenarios, 1415 steps — all passing** (post Batch 3). Runner at `middens/tests/cucumber.rs`. Feature files organized by domain under `middens/tests/features/`. Python technique tests at `tests/features/techniques/python_batch{1,3}.feature` (batch1 covers Batches 1+2 scripts despite the name; batch3 adds the 5 new ones).

## Process

### Adversarial development (foundry-style)

Non-trivial features use red/green adversarial process:
1. Write NLSpec (Why/What/How/Done) — review before proceeding
2. Red team (Codex or Gemini 3.1 Pro) writes Cucumber tests from DoD only
3. Green team (different model: Kimi K2.5 via OpenCode bash heredoc, or Gemini) implements from How section only
4. Run tests, send PASS/FAIL only to green team (no assertion text or error messages)
5. When tests fail: classify (contract gap / red bug / green bug / improvement), route to correct team
6. **Never adapt tests to match unauthorized API deviations** — amend the spec or reject

**Model selection (validated by Batches 1+2+3):**
- Red team: Gemini 3.1 Pro Preview (quality default — fewer iterations than 2.5 Pro)
- Green team: Kimi K2.5, GLM 5.1, or Minimax M2.7 via OpenCode — use the opencode-cli skill reference. Codex is quota-limited; don't rely on it as fallback.
- One file per Kimi invocation (write tool corrupts JSON payloads; use bash heredoc)
- Never use the same model for red and green

**OpenCode dispatch pattern (the hard-won-right-way — see `~/.claude/skills/opencode-cli/`):**

```bash
opencode run \
  --model kimi-for-coding/k2p5 \
  --format json \
  --variant high \
  -f /tmp/shared-contract.md \
  -f /tmp/per-technique-how.md \
  "Implement the technique per the attached contract and algorithm. Write via bash heredoc." \
  < /dev/null 2>/dev/null \
  | jq -r 'select(.type == "text") | .text' \
  > /tmp/green-output.md
```

**Correct model IDs (validated against `opencode models` 2026-04-06):**
- `kimi-for-coding/k2p5` — Kimi K2.5
- `kimi-for-coding/kimi-k2-thinking` — Kimi K2 Thinking (reasoning-heavier; try this when k2p5 gets stuck)
- `zai-coding-plan/glm-5.1` — GLM 5.1
- `minimax-coding-plan/MiniMax-M2.7` — Minimax M2.7 (NOT `minimax/minimax-m2.7` — old ID fails silently)
- `opencode/minimax-m2.5-free` — free tier
- `perplexity/sonar` — web search

**OpenCode gotchas (from the skill, validated by Batch 3 mistakes):**
1. **Always** `--format json` + `jq -r 'select(.type == "text") | .text'` to get clean output. Raw JSONL is 90KB of protocol noise.
2. **Always** `< /dev/null 2>/dev/null` when piping — prevents stale stdin and stderr contamination.
3. **Always** `wait` after backgrounded `&` dispatches — without it the parent shell exits before OpenCode finishes, producing empty logs. This was the "SQLite WAL conflict" I originally misdiagnosed in Batch 3.
4. **Use `-f <file>` to attach context files**, DON'T reference paths in the prompt text. OpenCode auto-rejects `external_directory` reads of `/tmp/*` via its permission layer — which is what killed ENA in Batch 3.
5. **Use `--variant high`** (or `max`) for reasoning-heavy work.
6. **Never use `-s false`** for OpenCode (that's a Gemini flag — stray `:false` directories get created via shell misinterpretation, contaminating the workspace).
7. Error events are nested 3 levels deep: `error.error.data.message`.
8. Invalid model IDs fail in ~1.5s — parse for fast failure.
9. No system prompt flag — concatenate SYSTEM + USER into the attached file or inline prompt.
10. No sandbox mode — review changes via `git diff` after.

**Parallel fan-out pattern (validated in refinery workflows):**

```bash
opencode run --model kimi-for-coding/k2p5 --format json -f /tmp/contract.md "Task A" < /dev/null 2>/dev/null | jq -r 'select(.type == "text") | .text' > a.md &
opencode run --model zai-coding-plan/glm-5.1 --format json -f /tmp/contract.md "Task B" < /dev/null 2>/dev/null | jq -r 'select(.type == "text") | .text' > b.md &
opencode run --model minimax-coding-plan/MiniMax-M2.7 --format json -f /tmp/contract.md "Task C" < /dev/null 2>/dev/null | jq -r 'select(.type == "text") | .text' > c.md &
wait  # CRITICAL — without this, the files will be empty
```

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
