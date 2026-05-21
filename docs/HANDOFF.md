# Session Handoff

**Last updated:** 2026-05-21 (Pi archive extension implemented)

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

**v0.0.1-beta.3 is now out.** The release matrix remains the narrowed 3-target set after the Intel-Mac runner starvation incident: `macos-14` (darwin-arm64), `ubuntu-latest` (linux-x86_64), and `ubuntu-24.04-arm` (linux-arm64). beta.1 added Pi coding-agent parser support; beta.2/beta.3 fixed two validation-discovered nondeterminism bugs (`information_foraging.py` set iteration and `tpattern_detection.py` unseeded permutation test). Release workflows completed successfully and emitted only GitHub's Node.js 20 deprecation warnings for v4 actions / `softprops/action-gh-release@v2`. The rationale doc at `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md` records the queue-starvation lesson as failure mode #6.

**GitHub Pages initial cut is also live** at <https://lightless-labs.github.io/third-thoughts/>. The `www` orphan branch is serving three static pages (`index.html`, `findings.html`, `report.html`). Mobile code blocks now preserve preformatted text and scroll horizontally instead of wrapping into soup (`www` commit `f01c672`). Follow-up polish is tracked in `todos/distribution-github-pages.md` and is no longer a release blocker.

**PR #2 status (2026-04-25):** merged to `main` as `4afbc19` (`Handle adaptive Codex reasoning observability (#2)`). Automated review cycle was run repeatedly (Codex, Gemini, CodeRabbit); CodeRabbit approved, Codex reported no major issues on the final pass, and the CodeRabbit status check was green before merge. Last local validation before merge: `cd middens && cargo test` → 341/341 scenarios, 1856/1856 steps; `cd middens && cargo build --release` → pass. Deferred follow-ups filed: `todos/codex-standalone-reasoning-response-items.md` and `todos/codex-typed-unknown-content-blocks.md`. Post-merge compounding landed in `e36f1a3`, creating `docs/solutions/methodology/codex-adaptive-reasoning-observability-20260425.md` and refreshing related parser/thinking-visibility docs.

**Session archive command is implemented** (commit `51ef8b6`, after NLSpec `68dee67` and red tests `fe51730`). `middens archive --to <dir> [--source ...] [--from ...] [--dry-run] [--yes] [--require-parseable]` discovers local agent JSONL stores, copies raw logs into a content-addressed archive, dedupes by SHA-256, writes `manifest.json` + `indexes/sessions.jsonl`, and never mutates source logs. Safety gates: explicit `--to`, `--yes` for non-dry-run, raw-transcript warning, dry-run writes nothing, source/archive overlap rejection, corrupt-manifest and drift failures, destination collision checks, lock file, git-worktree `.gitignore`, parser enrichment with strict `--require-parseable`. Validation: `cd middens && cargo test` → 375/375 scenarios, 2081/2081 steps; `cd middens && cargo build --release` → pass.

**Pi archive automation extension is implemented:** `integrations/pi/middens-archive/` is a Pi package with a TypeScript extension, README, `package.json`, lockfile, and `tsconfig`; the repo root also has a small Pi package manifest so a git install of the repo can find the extension. It registers `/middens-archive-now` and `/middens-archive-status`, schedules debounced non-overlapping periodic archives, and runs a bounded best-effort shutdown archive only after the interval has elapsed. Configuration is explicit via `MIDDENS_ARCHIVE_ROOT` (no default path); optional env vars cover interval, middens binary, normal timeout, and shutdown timeout. Validation run in-session: `cd integrations/pi/middens-archive && npm run check` passes; `pi --no-extensions --offline --no-session -e ./integrations/pi/middens-archive -p /middens-archive-status` with unset root reports disabled; temp-`HOME` fixture plus source-built `middens` and `/middens-archive-now` writes `manifest.json`, `indexes/sessions.jsonl`, and one content-addressed object; `PI_CODING_AGENT_DIR=$(mktemp -d) pi install ./integrations/pi/middens-archive` succeeds. Todo `todos/archive-pi-extension-auto-backup.md` is marked done. Claude Code and Codex automation todos remain research-first because their hook/plugin surfaces still need checking; if no stable APIs exist, document wrapper/LaunchAgent/systemd timer fallbacks rather than pretending a cron job is a plugin in a fake moustache.

**Next concrete move:** if continuing data-retention work, research the Claude Code and Codex hook/plugin surfaces (`todos/archive-claude-code-plugin-auto-backup.md`, `todos/archive-codex-plugin-auto-backup.md`). Otherwise choose the next P1 research follow-up (HSMM re-run with Boucle excluded, autonomous session stratum, or multilingual remediation) unless a distribution patch release is desired for `middens archive` and the new Pi package. Distribution Step D remains complete: source-built `middens 0.0.1-beta.3` and Homebrew-installed `middens 0.0.1-beta.3` were run against the same 10-session public `badlogicgames/pi-mono` slice with `--all`; manifests/parquet/notebook structure matched after normalizing expected run IDs/timestamps and allowing tiny floating-point tolerance. Apple Silicon Homebrew was validated with `brew reinstall`, `middens --version`, `brew test`, and `brew audit`. The default install pulls `uv` as a recommended dependency; `--without-uv` was validated previously for beta.0.

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
| Parsers | Done | Claude Code (incl. new format types), Codex, OpenClaw, Pi coding-agent / `pi-share-hf` JSONL (Gemini stub) |
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
| Test suite | **375/375 passing** | 2081 steps (`cd middens && cargo test`, after archive command, 2026-05-21) |

---

## Open work (prioritized)

### P0 — Distribution (remaining blockers)

Remaining blocking steps. See individual `todos/distribution-*.md` for detail.

1. ~~**Step A — e2e verb**~~ **DONE** (`middens run`, commit `7aea3c6`). Chains analyze → interpret → export. `--model` optional; omit to skip interpret. Hard-fails on interpret error.

2. ~~**Step B — release workflow**~~ **DONE** (commit `49d896f`; matrix narrowed 2026-04-18 after Intel-Mac runner starvation on first tag cut). `.github/workflows/release.yml` triggers on `v*` tag. Native GH-hosted runners (no `cross`): `macos-14` (darwin-arm64), `ubuntu-latest` (linux-x86_64), `ubuntu-24.04-arm` (linux-arm64, free for public repos). `x86_64-apple-darwin` dropped — `macos-13` is queue-starved on free public repos and the first tag cut sat 9h waiting for a runner. Tarballs + per-artifact SHA256 + combined SHA256SUMS via `softprops/action-gh-release@v2`. Windows left as future stretch. Rationale + failure-mode log at `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md`. Follow-up todos from the pre-tag codex review: `todos/release-workflow-pin-actions-and-toolchain.md` (P2), `todos/release-workflow-orphan-sha256-sidecars.md` (P3).

3. ~~**Step C — Homebrew tap**~~ **DONE** (2026-04-27; refreshed 2026-05-20): tap repo created at <https://github.com/Lightless-Labs/homebrew-tap>. Formula installs `v0.0.1-beta.3` release binaries for Apple Silicon macOS, x86_64 Linux, and arm64 Linux. `uv` is `recommended`, not required; `--without-uv` and default install paths were validated for beta.0, and beta.3 was validated locally on Apple Silicon with default dependencies plus `brew test` and `brew audit`. Tap naming decision: generic `homebrew-tap`, yielding `brew install lightless-labs/tap/middens`. (`todos/distribution-homebrew-tap.md`)

4. ~~**Step D — two validation runs**~~ **DONE** (2026-05-20): source-built run vs brew-installed run completed on the same 10-session public Pi coding-agent Hugging Face slice. Both ran 23 techniques; manifests/parquet/notebook structure matched after expected run-id/timestamp normalization and tiny float tolerance. Validation found and fixed two nondeterminism bugs before the final beta.3/tap pass. (`todos/distribution-validation-runs.md`)

5. ~~**Step E — GitHub Pages landing page**~~ **INITIAL CUT SHIPPED** (2026-04-18). Site live at <https://lightless-labs.github.io/third-thoughts/>. Homebrew install story refreshed 2026-04-27. Remaining non-blocking site follow-ups live in `todos/distribution-github-pages.md` (embedded validation reports, contribution surface, second copy review, roadmap teaser).

### P0 — Next distribution/data-retention work

- ~~**Session-log backup/archive**~~ **DONE** (2026-05-21, commit `51ef8b6`): `middens archive` discovers supported local session stores, copies raw JSONL logs into a user-controlled content-addressed archive, deduplicates by SHA-256, records object/observation manifest entries, supports dry-run, and never mutates source logs. Built via NLSpec + red/green adversarial process because raw private data plumbing should be boring and a little paranoid. (`todos/session-log-backup-archive.md`)

### P1 — Archive automation improvements

- ~~**Pi extension for automatic archives**~~ **DONE** (2026-05-21): package lives at `integrations/pi/middens-archive/`; registers `/middens-archive-now` and `/middens-archive-status`; uses explicit `MIDDENS_ARCHIVE_ROOT`; debounces periodic/shutdown runs and blocks overlap. Typechecked and smoke-tested with temp `HOME` fixture. (`todos/archive-pi-extension-auto-backup.md`)
- **Claude Code hook/plugin for automatic archives**: Research Claude Code's current plugin/hook surface first. If supported, add an integration that invokes `middens archive --source claude-code`; otherwise document an explicit wrapper/scheduler fallback. (`todos/archive-claude-code-plugin-auto-backup.md`)
- **Codex hook/plugin for automatic archives**: Research Codex CLI plugin/hook support first. If supported, add an integration that invokes `middens archive --source codex`; otherwise document an explicit wrapper/scheduler fallback. (`todos/archive-codex-plugin-auto-backup.md`)

### P1 — Research follow-ups

- **HSMM re-run with Boucle excluded**: The 24.6× pre-failure lift collapsed to 2.15× on the 2026-04-14 run. Direction replicates but magnitude is suspect — likely Boucle contamination. Re-run with W10–W12 stripped and stratified. Update finding status in CLAUDE.md accordingly.
- **Autonomous session stratum**: `SessionType::Autonomous` classifier + `corpus-split/autonomous/` bucket. Full plan at `todos/autonomous-session-stratum.md`. Required for the 4-axis compound scoping rule. Phase 2: run 23-technique battery on the new stratum.
- **Multilingual remediation**: implement language detection + refusal on `thinking-divergence`, `correction-rate` lexical layer, `user_signal_analysis`. Adds `whatlang` (or equivalent). Populates `Session::language`. Then re-run risk-suppression replications under `language=en` gate. (`todos/multilingual-text-techniques.md`)

### P2 — Tech debt

- **CLI version at message level**: `Message::version` + `SessionMetadata::versions: Vec<String>` — enables corpus stratification by Claude Code CLI version. (`todos/message-level-version-field.md`)
- **Frustration classifier recalibration**: 90% of user signals pile up at intensity 2. Needs rescaling or model change. (`user_signal_analysis.py`)
- Deferred PR review items: `todos/batch4-coderabbit-deferred.md`, `todos/batch3-coderabbit-deferred.md`
- Todos filed but not started: `fingerprint-technique-retrofit.md`, `corpus-timeline-deletion.md`, `batches-1-2-pii-and-type-audit.md`, `interpret-parser-strictness.md`, `interpret-export-split-composition.md`

### P2 — Pre-release review follow-ups (filed 2026-04-18, post v0.0.1-beta.0 tag)

From the codex xhigh pre-tag review (two rounds). None were beta-tag blockers; the five round-1 blockers and two round-2 blockers were fixed in-session. Remaining should-fix items:

- `todos/middens-hide-unimplemented-subcommands.md` — `report`/`fingerprint` print `[not yet implemented]`; hide or implement
- `todos/middens-export-dir-mismatch-validation.md` — `export --analysis-dir A --interpretation-dir B` silently accepts mismatched dirs
- `todos/repo-root-readme-stale-findings.md` — repo-root README quotes pre-stratification finding magnitudes
- `todos/middens-privacy-flags-inconsistent-across-verbs.md` — `--include-project-names` is a partial no-op on `interpret`/`export` because parquet is frozen at analyze time
- `todos/middens-scrub-test-coverage-weakness.md` — cucumber assertions check key presence, not value shape; regression that leaks raw path would still pass

### P3 — Pre-release review nice-to-haves

- `todos/middens-run-verb-force-flag-hardcoded.md` — `run` hardcodes `force: true` on export; standalone `export` defaults to `false`
- `todos/release-workflow-orphan-sha256-sidecars.md` — workflow generates per-tarball `.sha256` sidecars but doesn't publish them

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
| `main` | Local `main` includes session archive work, archive-automation todo docs, and the Pi archive extension package (latest local commit). `origin/main` still includes beta.3 (`4bcdd35`); tag `v0.0.1-beta.3` peels to `4bcdd35`. |

No open PRs. No feature branches.

### Local working tree

- No tracked working-tree changes expected after the Pi archive extension commit.
- `www` branch landing-page Linux tarball copy was pushed as `0188acc`; mobile code-block wrapping fix was pushed as `f01c672`.
- Tap formula was updated to `v0.0.1-beta.3` and pushed to `Lightless-Labs/homebrew-tap` as `74bf114`.
- Untracked analysis output: `middens-results/` (local run artifacts; do not commit blindly)
- Homebrew side effect: `middens` is currently installed from `lightless-labs/tap` at `0.0.1-beta.3`; `uv` is installed because the default install path was validated.

---

## Test suite

**375/375 Cucumber scenarios, 2081 steps — all passing.**

Last Rust run: 2026-05-21, after `middens archive` implementation.

Run: `cd middens && cargo test`

Pi extension validation (2026-05-21): `cd integrations/pi/middens-archive && npm run check`; `pi -e ./integrations/pi/middens-archive -p /middens-archive-status` with temp `HOME` and unset root; temp-`HOME` `/middens-archive-now` smoke using source-built `middens`; temp `PI_CODING_AGENT_DIR` local package install smoke for both subpackage and repo-root manifests.

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
