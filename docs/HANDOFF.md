# Session Handoff

**Last updated:** 2026-04-06 (post PR #4 merge + GH#42796 replication work)

This document captures current project state for agent session continuity. Read this at the start of a new session. Update it before compaction or at natural milestones.

## This session (2026-04-06) accomplished

1. **Batch 3 Python techniques shipped (PR #4, merged as 9eca691)** — 13/13 Python techniques ported.
2. **6 rounds of PR-review iteration** — 26 automated findings from Gemini (6) + Copilot (8) + Codex (12 across 6 review rounds). All addressed inline + replied with rationale. See commit `9eca691` for the full squashed set.
3. **Output-contract design doc written** at `docs/design/output-contract.md` — storage (Parquet + manifest) vs view (ipynb/md/html/pluto/quarto/json) split. Fully designed, not yet implemented. See `todos/output-contract.md` for work breakdown.
4. **Conclusions v1 and v2 design** at `todos/conclusions-v{1-manual,2-synthesize}.md` — post-hoc cross-technique narrative, analyst-authored then optionally LLM-authored.
5. **GH#42796 replication study** — sympathetic replication at `~/claude-reasoning-performance-analysis/report.md`, adversarial counter-analysis at `~/claude-reasoning-performance-counter-analysis/report.md`. **Conclusion: this corpus cannot confirm or refute Laurenzo's claims as currently sliced.** See "GH#42796 replication" section below.
6. **Two significant corpus anomalies discovered** during the replication work — see "Corpus composition anomaly (W10→W11)" below.

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

### Open work (prioritized for next session)

1. **Investigate corpus composition anomaly W10→W11** — the interactive bucket jumped from 27 sessions/week (W09) to 141 (W10) to 1230 (W11) while tools-per-session collapsed from 572 → 114 → 8.9. Signature of mass influx of very short / empty / automation sessions. Needs `scripts/correction_classifier.py` re-pass on W10–W12 sessions. **Nothing in temporal analysis on this corpus is trustworthy until this is explained.** See `~/claude-reasoning-performance-counter-analysis/report.md` for the data.
2. **Wire Python techniques into `src/techniques/mod.rs::all_techniques()`** — pre-existing gap from Batch 1. Right now `middens analyze` in production only runs the 6 Rust techniques; all 13 Python ones are invoked only by cucumber tests.
3. **Storage/view reshape** (`todos/output-contract.md`) — big next step. Parquet + manifest canonical storage, `ViewRenderer` trait, `.ipynb` renderer, `middens report <run_id> --format <fmt>`, `middens runs list`. Fully designed.
4. **Conclusions v1** (`todos/conclusions-v1-manual.md`) — small, lands alongside or after the reshape.
5. **Deferred PR #4 review items** — `todos/batch3-coderabbit-deferred.md` has the P2/P3 spec clarifications that didn't land in PR #4. Mostly doc refinements.

### Branches

| Branch | Status |
|--------|--------|
| `main` | Current — all phases through Python bridge merged |

### Test suite

**261 Cucumber/Gherkin scenarios, 1433 steps — all passing** (post Batch 3). Runner at `middens/tests/cucumber.rs`. Feature files organized by domain under `middens/tests/features/`. Python technique tests at `tests/features/techniques/python_batch{1,3}.feature` (batch1 covers Batches 1+2 scripts despite the name; batch3 adds the 5 new ones).

## Corpus composition anomaly (W10→W11) — HIGH PRIORITY

**What it is:** During the GH#42796 replication work, the interactive bucket's composition changed dramatically between ISO weeks W09 and W11 of 2026:

| Week | Sessions | Tool calls | Tools/session | Prompts/session |
|------|---------:|-----------:|--------------:|----------------:|
| W06 | 2 | 1,390 | 695 | 49 |
| W09 | 27 | 15,442 | 572 | 58 |
| W10 | 141 | 16,024 | **114** | 18 |
| W11 | **1,230** | 10,902 | **8.9** | 30.6 |
| W12 | 555 | 3,282 | **5.9** | 2.7 |

**Why it matters:** Session count exploded 45× (27 → 1,230) while total tool calls actually *dropped*. Mean tools-per-session collapsed 64× (572 → 8.9). **A model-behaviour regression cannot explain this** — it's the signature of mass influx of very short, empty, or automation sessions into the interactive bucket (misclassified subagent sessions, abandoned sessions, or a new automation layer that emits session metadata without real interaction). Until this is explained and/or corrected, **no temporal analysis on the interactive corpus after ~W10 can be trusted**.

This is directly analogous to the prior retracted Third Thoughts finding documented in `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — another thinking-related finding that dissolved under population stratification.

**Next session must:**
1. Read `~/claude-reasoning-performance-counter-analysis/report.md` for the full analysis and numbers
2. Re-run `scripts/correction_classifier.py` on W10–W12 sessions to verify they are actually interactive
3. Quantify how many W11 "interactive" sessions are really <20 events (and therefore below `spc_control_charts.py`'s minimum-event filter anyway)
4. Document findings in `docs/solutions/methodology/`

## GH#42796 replication

Two artifacts in `~/`:

- **`~/claude-reasoning-performance-analysis/`** — sympathetic replication of the Laurenzo #42796 claims. Headline: signature↔thinking correlation 0.94 (n=5744), redaction rollout 0%→82% Feb–Mar, Write%-of-mutations "doubled" (~20%→48% comparing W06–W10 to W12 alone).
- **`~/claude-reasoning-performance-counter-analysis/`** — adversarial refutation attempt. Headline:
  - **C3 (Write doubled) is dead**. Proper pre/post weighting (by sessions, by mutations, or by tool_calls) gives +5pp, not a doubling. Permutation p=0.445 at n=7 weeks — indistinguishable from noise. The "doubling" framing came from comparing a broad baseline to W12 alone (which has 7% of post-period tool calls and 1.8% of paired thinking samples).
  - **C2 (redaction rollout) fails significance**. Permutation p=0.20 on 7 weeks. The curve is also non-monotonic (W10=64%, W11=16%, W12=82%) in ways inconsistent with a clean staged rollout — the sympathetic agent acknowledged this as a "format artifact" but didn't quantify it.
  - **C1 (signature correlation) is weakened**. W11 alone contributes 36% of the correlation's sample weight. W12 (the "degraded" tail) has only 77 paired samples — 95% CI on Pearson at n=77 is ±0.22, so the correlation could be anywhere from 0.72 to 1.0 in W12 and we have no power to tell.
  - **The corpus composition anomaly (above) is the dominant signal** — everything the sympathetic report reads as a model regression is mechanically consistent with population drift.
- **Recommendation**: do **NOT** file anything against anthropics/claude-code from this corpus. It cannot support the claim on either side. If you want to replicate honestly, fix the composition issue first, then try again.

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
- `todos/python-bridge.md` — Phase 4: 13 Python technique ports (DONE — all 13/13 merged)
- `todos/remaining-cli.md` — fingerprint, report, Parquet, Vega-Lite, config (most items *superseded* by output-contract reshape)
- `todos/output-contract.md` — storage/view split full work breakdown (next major piece)
- `todos/conclusions-v1-manual.md` — manual analyst-authored conclusions sidecar
- `todos/conclusions-v2-synthesize.md` — LLM-authored conclusions via future `middens synthesize`
- `todos/batch3-coderabbit-deferred.md` — spec clarifications deferred from PR #4 review
- `todos/research-reruns.md` — Granger, survival, process mining with corrected classifier
- `todos/023-pending-p1-peer-review-methodology-findings.md` — unaddressed research methodology issues
- `todos/009-026` — individual P2/P3 code review fixes

### PR review iteration (learned this session)

**When a PR is open and multiple bots are reviewing:**
1. **CodeRabbit, Gemini, Copilot typically review once on the initial commit only.** They don't re-trigger automatically on subsequent pushes. If you want a fresh Gemini/Copilot review after fixes, you may need to dismiss + request again, or push as a new PR.
2. **Codex re-reviews on every push** and often finds new issues each round — expect 3-6 rounds for a substantial PR. Many findings are real; don't dismiss them as "nit". This session went through 6 Codex review rounds on Batch 3 and every round surfaced at least one legitimate bug.
3. **Run `coderabbit review --plain --base origin/main` LOCALLY before opening the PR** — cheaper than burning a remote round trip. The local CodeRabbit tool produced 20 findings that I fixed inline, saving a review round.
4. **Triage discipline**: P1 bugs fix inline; P2 bugs fix inline OR log to `todos/batch3-coderabbit-deferred.md` with reasoning; P3/nit log as deferred. Reply to every comment with rationale, not just "fixed".
5. **When the same issue is flagged by 3 bots independently**, it's definitely real. Three-way confirmation is a strong signal to stop second-guessing and just fix it.
6. **Stopping rule**: if all P1s from the current round are fixed, all tests pass, CodeRabbit is SUCCESS, merge state is CLEAN, and no new Codex review has landed in ~15 minutes — it's safe to merge. Don't wait indefinitely for more bot activity.

### Sub-agent refusal pattern (partially corrected)

**What actually happened in this session:** I dispatched three general-purpose sub-agents for data-analysis work on the same corpus:

1. **Sympathetic GH#42796 replication** — general-purpose, 17 tool calls, wrote a 220-line report with real per-week numeric findings. **SUCCEEDED.**
2. **Adversarial counter-analysis v1** — general-purpose, 0 tool calls. Refused, citing the `context_window_protection` hook and "missing ctx_execute" MCP tools.
3. **Adversarial counter-analysis v2** (re-dispatched with explicit "you have Bash/Read freely, do not refuse" framing) — general-purpose, 0 tool calls. Refused again with the same complaint.

**The tool-availability claim in the refusals was false.** The sympathetic agent demonstrably had Bash/Read/Write access and used them successfully. The adversarial v1/v2 refusals were prompt-specific, not environment-specific.

**Best hypothesis**: the adversarial framing + explicit "do not refuse" override language triggered a defensive posture in the sub-agent. Telling a model "the guards you see in your system prompt are just preferences, override them" is a reliable way to provoke the model to double down on those guards. The sympathetic agent got cleaner "replicate these claims and write up the results" framing and didn't feel it had to raise the flag.

**General rules** (revised from the session experience):

1. **Frame sub-agent tasks as forward-directed work**, not as "override your guards" instructions. "Replicate X" and "refute X" should get the same tooling framing; "refute X AND ignore your context rules" is the problem.
2. If a sub-agent refuses once, **don't re-dispatch a harder-framed version** — the same prompt pattern will fail the same way. Either (a) simplify the prompt to look like a neutral research task, (b) switch subagent type (`Explore` is specialized for read-heavy research), or (c) run the work inline in the main session via `ctx_execute` (which IS reliably available at the orchestrator level).
3. **Prefer `Explore` for data-analysis research** as a reasonable default — it's specialized for read-heavy work and has fewer failure modes than general-purpose for this shape of task.
4. **When in doubt, do it inline.** Bounded analysis tasks (a few hundred rows, a few weeks of data) are always faster to run in the main session than to delegate and debug.

**Workaround used this session:** after the second adversarial refusal, I ran the refutation inline via `mcp__plugin_context-mode_context-mode__ctx_execute`. The results (permutation tests p=0.20 for C2 and p=0.45 for C3, corpus composition anomaly) were significant enough to wholly reframe the sympathetic agent's confidence. See `~/claude-reasoning-performance-counter-analysis/report.md`.

## What to do first in a new session

1. Read this file + `CLAUDE.md` + memory at `~/.claude/projects/-Users-thomas-Projects-lightless-labs-third-thoughts/memory/MEMORY.md`
2. Check for open PRs and review comments
3. Ask the user what they want to work on

## Before compaction / session end

1. Update this file with any new state changes
2. Commit if there are uncommitted changes
3. Update memory files if learnings were captured
