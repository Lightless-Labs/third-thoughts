# Session Handoff

**Last updated:** 2026-04-17 (distribution Step B done; Step C Homebrew tap is next)

Read this at the start of every session. Update before compaction or at natural milestones.

---

## >>> Read this first <<<

**All 23 techniques are working. Zero errors, zero timeouts on 13,423 sessions (commit `867f57b`).**

The two blocking timeouts (`prefixspan-mining`, `cross-project-graph`) are fixed. Granger-causality (prior None-guard fix) is also clean. The parser now handles newer Claude Code session log formats (`file-history-snapshot` preamble, empty placeholder files).

Full-corpus validation result (2026-04-14, 13,423 sessions, `--all`):

| Result | Count | Notes |
|--------|-------|-------|
| Completed | 23/23 | All Rust + 17 Python techniques |
| Failed | 0 | — |
| Timed out | 0 | — |

**Distribution workstream is now unblocked.** All three prior blocking conditions are met: repo hygiene done, CLI triad (analyze/interpret/export) done, 23/23 techniques working on a full corpus.

**Next concrete move:** Distribution Step C — Homebrew tap (`todos/distribution-homebrew-tap.md`). Steps A (`middens run`, `7aea3c6`) and B (release workflow, `49d896f`) are done. Tap repo name is the open question (`Lightless-Labs/homebrew-tap` generic vs `Lightless-Labs/homebrew-middens` single-formula).

---

## What's built

`middens` is a usable end-to-end CLI for analyzing AI agent session logs.

```bash
middens run corpus-full --all --model claude-code/claude-opus-4-6 -o report.ipynb  # full pipeline
middens analyze corpus-full --all                     # full 23-technique battery
middens analyze corpus-full --all --timeout 1800      # explicit timeout override
middens analyze path/ --split                          # stratify by session type
middens analyze path/ --techniques markov,entropy      # subset
middens interpret --model claude-code/claude-opus-4-6 # LLM interpretation of last run
middens export --format jupyter                        # notebook from last run
middens parse file.jsonl                               # single file debug
middens freeze corpus/ -o manifest.json                # corpus snapshot
middens list-techniques                                # 23 registered techniques
```

### Implementation status

| Component | Status | Notes |
|-----------|--------|-------|
| Parsers | Done | Claude Code (incl. new format types), Codex, OpenClaw (Gemini stub) |
| Classifiers | Done | Message (5-priority) + session type (interactive/subagent) |
| Corpus discovery | Done | Recursive scan, symlink following, auto-discover |
| Techniques (Rust) | Done (6) | markov, entropy, diversity, burstiness, correction-rate, thinking-divergence |
| Techniques (Python) | Done (17) | Batches 1–4, all wired, all completing on full corpus |
| Python asset embedding | Done | Scripts baked into binary, extracted at runtime — no source tree needed |
| Python bridge | Done | UvManager + PythonTechnique wrapper; shared session cache (one serialise, not 17×) |
| Dynamic timeout | Done | `clamp(100×ln(n), 60, 1800)` — ~951s at 13k sessions |
| Storage (Parquet) | Done | One Parquet per technique + `manifest.json` per run, XDG paths |
| View layer | Done | `ViewRenderer` trait, `ipynb.rs` (v4 nbformat) |
| `analyze` command | Done | Full triad shape: discovers → parses → techniques → Parquet + manifest |
| `interpret` command | Done | Runner abstraction (4 providers), fallback chain, atomic write |
| `export` command | Done | Jupyter notebook; works without interpretation |
| `run` command | Done | Chains analyze → interpret → export; hard-fails on any stage error |
| CLI validation | Done | `--force` requires `--timeout`; timeout skipped when `--no-python` |
| Test suite | **333/333 passing** | 1810 steps |

---

## Open work (prioritized)

### P0 — Distribution (now unblocked)

All five steps in order. See individual `todos/distribution-*.md` for detail.

1. ~~**Step A — e2e verb**~~ **DONE** (`middens run`, commit `7aea3c6`). Chains analyze → interpret → export. `--model` optional; omit to skip interpret. Hard-fails on interpret error.

2. ~~**Step B — release workflow**~~ **DONE** (commit `49d896f`). `.github/workflows/release.yml` triggers on `v*` tag. Native GH-hosted runners (no `cross`): `macos-14` (darwin-arm64), `macos-13` (darwin-x86_64), `ubuntu-latest` (linux-x86_64), `ubuntu-24.04-arm` (linux-arm64, free for public repos). Tarballs + per-artifact SHA256 + combined SHA256SUMS via `softprops/action-gh-release@v2`. Windows left as future stretch. Rationale documented at `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md`.

3. **Step C — Homebrew tap** ← **next**: `brew install lightless-labs/tap/middens`. `uv` is a `recommend` not a `depend`. crates.io secondary. Open question: tap repo name (`Lightless-Labs/homebrew-tap` generic vs `Lightless-Labs/homebrew-middens` single-formula). (`todos/distribution-homebrew-tap.md`)

4. **Step D — two validation runs**: source-built run vs brew-installed run on same corpus; exports must be structurally identical. Open question: use full private corpus (PII risk on landing page) or create a small public fixture corpus? (`todos/distribution-validation-runs.md`)

5. **Step E — GitHub Pages landing page**: orphan `www` branch, static HTML/CSS, no JS framework. Copy reviewed by Gemini 3.1 Pro + Codex xhigh. Open questions: domain, design polish level, first-draft ownership. (`todos/distribution-github-pages.md`)

### P1 — Research follow-ups

- **HSMM re-run with Boucle excluded**: The 24.6× pre-failure lift collapsed to 2.15× on the 2026-04-14 run. Direction replicates but magnitude is suspect — likely Boucle contamination. Re-run with W10–W12 stripped and stratified. Update finding status in CLAUDE.md accordingly.
- **Autonomous session stratum**: `SessionType::Autonomous` classifier + `corpus-split/autonomous/` bucket. Full plan at `todos/autonomous-session-stratum.md`. Required for the 4-axis compound scoping rule. Phase 2: run 23-technique battery on the new stratum.
- **Multilingual remediation**: implement language detection + refusal on `thinking-divergence`, `correction-rate` lexical layer, `user_signal_analysis`. Adds `whatlang` (or equivalent). Populates `Session::language`. Then re-run risk-suppression replications under `language=en` gate. (`todos/multilingual-text-techniques.md`)

### P2 — Tech debt

- **CLI version at message level**: `Message::version` + `SessionMetadata::versions: Vec<String>` — enables corpus stratification by Claude Code CLI version. (`todos/message-level-version-field.md`)
- **Frustration classifier recalibration**: 90% of user signals pile up at intensity 2. Needs rescaling or model change. (`user_signal_analysis.py`)
- Deferred PR review items: `todos/batch4-coderabbit-deferred.md`, `todos/batch3-coderabbit-deferred.md`
- Todos filed but not started: `fingerprint-technique-retrofit.md`, `corpus-timeline-deletion.md`, `batches-1-2-pii-and-type-audit.md`, `interpret-parser-strictness.md`, `interpret-export-split-composition.md`

### P3 — NLSpec / run verb follow-ups (filed 2026-04-16)

- `todos/run-verb-nlspec-dry-run-semantics.md` — clarify `--dry-run` + export behavior contradiction
- `todos/run-verb-nlspec-acceptance-criteria.md` — expand Done section with 6 missing test cases
- `todos/run-verb-output-path-validation.md` — preflight check on `-o` before analyze runs
- `todos/dynamic-timeout-formula-symbols.md` — stale formula in timeout todo (implemented as `clamp(100×ln(n), 60, 1800)`; doc needs updating)

---

## Key findings (current)

| Finding | Status | Evidence |
|---------|--------|----------|
| 99.99% risk suppression on visible-thinking sessions | **Strengthened** (2026-04-14) | N=4,518 sessions, 31,679 risk tokens, 2 leaks. `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md` |
| 85.5% risk suppression on mixed corpus | **SUPERSEDED** | Mixed-corpus artifact. |
| HSMM pre-failure state (24.6× lift) | **Provisional — magnitude unconfirmed** (2.15× on 2026-04-14 run) | Direction holds; 24.6× likely Boucle artifact. Needs re-run with W10–W12 excluded. |
| MVT violated (agents under-explore) | Robust | `experiments/full-corpus/information-foraging.md` |
| Thinking blocks prevent corrections | **RETRACTED** | Did not survive population split. |
| Session degradation (agents get worse) | Holds on interactive only | `experiments/interactive/survival_analysis.txt` |
| W10–W12 Boucle contamination | **Confirmed** (PR #6) | 1,820/1,826 sessions, 100% zero tool calls. |
| Correction front-loading | New (2026-04-14) | 0.068 first-third vs 0.019 last-third — sessions improve, not degrade. |
| Sequential motifs | New (2026-04-14) | UWUW = success, UUX = struggle, UC→UC self-reinforces (z=889.5). |
| Epistemic network discriminator | New (2026-04-14) | EVIDENCE_SEEK ↔ SELF_CORRECT discriminates success; plan-frame loops predict failure. |

Full Opus 4.6 interpretation at `~/middens-analysis-2026-04-14/interpretation.{md,pdf}`.

**Compound scoping rule:** every future headline finding on thinking or text behaviour must be scoped on 4 axes: `session_type ∈ {Interactive, Subagent, Autonomous}`, `thinking_visibility ∈ {Visible, Redacted, Unknown}`, `language ∈ {en, other}`, and a temporal window. A finding that doesn't survive all four is not a finding.

**CLI version axis (pending):** `cli_version` is a candidate 5th axis — the `version` field is present on every JSONL line and spans 2.1.36–2.1.92 in the current corpus. Requires P2 todo `message-level-version-field.md` before it can be used for stratification.

---

## Branch state

| Branch | Status |
|--------|--------|
| `main` | All work landed here. 13 commits since last push to origin/main (release workflow + compound learning). |

No open PRs. No feature branches.

---

## Test suite

**333/333 Cucumber scenarios, 1810 steps — all passing.**

Run: `cd middens && cargo test`

---

## Python technique notes (for new work on Python techniques)

- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout
- Tables: `{"name": ..., "columns": [...], "rows": [[...]]}` — rows are `List[List[Value]]`, NOT dicts. Recurring gotcha.
- `tool_calls[].input` is a dict — extract keys like `input.get("path")`
- `tool_results[].tool_use_id` not `id`
- Roles are `User`/`Assistant` (PascalCase)
- Always sanitize NaN/Infinity before `json.dumps`
- Empty/insufficient sessions: return valid result with "insufficient" in summary, NOT error exit
- Test fixtures have `timestamp: None` — fall back to array index ordering
- `extract_tool_sequences()` skips no-tool-call sessions — don't use session indexes to index into its output

---

## Institutional knowledge

Key solutions docs for common failure modes:

- `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md` — native GH-hosted runner matrix for cross-platform Rust CLI releases (no `cross`)
- `docs/solutions/performance-issues/prefixspan-closed-flag-quadratic-timeout-20260413.md` — O(n²) from `closed=True`
- `docs/solutions/performance-issues/cross-project-graph-per-project-regex-loop-timeout-20260413.md` — O(n×m×p) regex loop
- `docs/solutions/best-practices/cli-flag-combination-validation-20260413.md` — validate flag pairs at parse time
- `docs/solutions/failure-modes/parser-probe-first-line-fragility-20260413.md` — KNOWN_TYPES staleness
- `docs/solutions/best-practices/three-gate-testing-unit-corpus-codex-20260414.md` — unit / full-corpus / Codex xhigh gates
- `docs/solutions/workflow-issues/codex-skill-auto-activation-20260409.md` — prefix Codex prompts with "DIRECT TASK — DO NOT invoke any skills"
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — always stratify
- `docs/solutions/methodology/full-corpus-23-technique-run-findings-20260414.md` — 2026-04-14 findings
