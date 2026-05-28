# Session Handoff

**Last updated:** 2026-05-26 (SWE-chat adapter extracted for dataset-specific parsing/materialization)

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

**v0.0.1-beta.4 is now out.** The release matrix remains the narrowed 3-target set after the Intel-Mac runner starvation incident: `macos-14` (darwin-arm64), `ubuntu-latest` (linux-x86_64), and `ubuntu-24.04-arm` (linux-arm64). beta.1 added Pi coding-agent parser support; beta.2/beta.3 fixed two validation-discovered nondeterminism bugs (`information_foraging.py` set iteration and `tpattern_detection.py` unseeded permutation test). beta.4 is the archive-support release: it advertises `middens archive` and the self-contained Pi / Claude Code / Codex archive plugins in release-facing docs. Release workflow `26325365657` completed successfully and emitted only GitHub's Node.js 20 deprecation warnings for v4 actions / `softprops/action-gh-release@v2`. Homebrew tap was updated to beta.4 at `Lightless-Labs/homebrew-tap@7d488f8` and validated locally (`brew reinstall`, `middens --version`, `brew test`, `brew audit --strict --online`). The rationale doc at `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md` records the queue-starvation lesson as failure mode #6.

**GitHub Pages initial cut is also live** at <https://lightless-labs.github.io/third-thoughts/>. The `www` orphan branch is serving three static pages (`index.html`, `findings.html`, `report.html`). Mobile code blocks now preserve preformatted text and scroll horizontally instead of wrapping into soup (`www` commit `f01c672`). Follow-up polish is tracked in `todos/distribution-github-pages.md` and is no longer a release blocker.

**PR #2 status (2026-04-25):** merged to `main` as `4afbc19` (`Handle adaptive Codex reasoning observability (#2)`). Automated review cycle was run repeatedly (Codex, Gemini, CodeRabbit); CodeRabbit approved, Codex reported no major issues on the final pass, and the CodeRabbit status check was green before merge. Last local validation before merge: `cd middens && cargo test` → 341/341 scenarios, 1856/1856 steps; `cd middens && cargo build --release` → pass. Deferred follow-ups filed: `todos/codex-standalone-reasoning-response-items.md` and `todos/codex-typed-unknown-content-blocks.md`. Post-merge compounding landed in `e36f1a3`, creating `docs/solutions/methodology/codex-adaptive-reasoning-observability-20260425.md` and refreshing related parser/thinking-visibility docs.

**Session archive command is implemented** (commit `51ef8b6`, after NLSpec `68dee67` and red tests `fe51730`). `middens archive --to <dir> [--source ...] [--from ...] [--dry-run] [--yes] [--require-parseable]` discovers local agent JSONL stores, copies raw logs into a content-addressed archive, dedupes by SHA-256, writes `manifest.json` + `indexes/sessions.jsonl`, and never mutates source logs. Safety gates: explicit `--to`, `--yes` for non-dry-run, raw-transcript warning, dry-run writes nothing, source/archive overlap rejection, corrupt-manifest and drift failures, destination collision checks, lock file, git-worktree `.gitignore`, parser enrichment with strict `--require-parseable`. Validation: `cd middens && cargo test` → 375/375 scenarios, 2081/2081 steps; `cd middens && cargo build --release` → pass.

**Self-contained archive automation plugins are implemented for Pi, Claude Code, and Codex.** The first Pi cut originally shelled out to `middens`; user feedback corrected that the integrations should be self-contained, so all three now package a bundled Node archiver that writes a `middens archive`-compatible shape (`manifest.json`, `indexes/sessions.jsonl`, content-addressed `objects/sha256/...`) without requiring the `middens` CLI on `PATH`. Configuration is explicit via `MIDDENS_ARCHIVE_ROOT` (no default path), with `MIDDENS_ARCHIVE_INTERVAL_MINUTES` for debounce timing. Pi lives at `integrations/pi/middens-archive/` and registers `/middens-archive-now` / `/middens-archive-status`. Claude Code lives at `integrations/claude-code/middens-archive/`, with marketplace metadata at `integrations/claude-code/.claude-plugin/marketplace.json`; it uses `SessionStart`, `UserPromptSubmit`, and `Stop` hooks plus `/middens-archive-now`. Codex lives at `integrations/codex/middens-archive/`, with local marketplace metadata at `integrations/codex/.agents/plugins/marketplace.json`; it declares lifecycle hooks and `middens-archive-now` / `middens-archive-status` skills. Validation run in-session: Pi `npm run check`; fixture archives for all three sources with temp `HOME`; Pi `pi -e` command smoke; Claude `claude plugin validate` for plugin and marketplace; Codex `codex plugin marketplace add ./integrations/codex --enable plugin_hooks` against temp `HOME`; hook wrapper fixture smokes for Claude/Codex. Todos `archive-pi-extension-auto-backup.md`, `archive-claude-code-plugin-auto-backup.md`, and `archive-codex-plugin-auto-backup.md` are marked done.

**Codex 5.5 xhigh archive-plugin review gate is complete.** Model availability was confirmed with `pi --list-models codex` (`openai-codex/gpt-5.5`), then the review was run through Pi with `--thinking xhigh`. Output is saved at `docs/reviews/2026-05-21-archive-plugins-codex-55-xhigh-pi.md`. Findings: three High/P1 issues and several lower-severity issues. Fixed: existing `.gitignore` protection now appends a managed blanket-ignore block, Pi auto-archive now runs immediately and forces bounded shutdown archive, symlinked-parent source/archive overlap is caught, missing option values fail clearly, Pi archive enrichment counts only the Pi session header ID, manual Claude/Codex docs no longer imply ambiguous positional archive roots, and Codex install docs include `--enable plugin_hooks`. The follow-up regression suite is also done at `integrations/tests/archive-plugin-regression.test.mjs`, runnable via `cd integrations/pi/middens-archive && npm test`; it covers identical bundled scripts, missing/flag-looking option values, no-`middens` PATH dependency, `.gitignore` protection, symlink overlap, Pi session-count enrichment, drift, and destination collisions. Validation after regression tests: `cd integrations/pi/middens-archive && npm test`; `cd integrations/pi/middens-archive && npm run check`; prior plugin validations remain recorded in the review doc.

**Fixed public HF HSMM cohort + Boucle-excluded re-run are complete** (2026-05-24). Builder: `scripts/build_public_hf_hsmm_cohort.py`. Gitignored artifacts: `experiments/hsmm-public-hf-fixed/` with manifest, raw pinned snapshots, normalized `Session[]`, legacy JSONL symlink cohorts, and result JSON/logs. Sanitized methodology write-up: `docs/solutions/methodology/fixed-public-hf-hsmm-rerun-20260524.md`. Primary inference datasets are `cfahlgren1/agent-sessions-list@10d6d295cb79a11194cfd93f0e9752b76889fbba` and `badlogicgames/pi-mono@dac2a1d3ba12dda597b973a791a77618ccb5f413`; `armand0e/badlogicgames-pi-mono-opus-filtered@32e67a8d04febcb38a2d28798a6d80fb41481a38` is cross-check only, and `archit11/claude-code-traces@416248040ba2c706c475bba238782c3e334fd4d8` is normalized as request/response trace rows but excluded from HSMM inference. Manifest: 825 object rows, 815 parseable JSONL transcript objects, 1 normalized Parquet trace object, 9 metadata objects excluded. Cohorts: baseline 633 sessions / 15,942 assistant turns / 640 corrections; Boucle-excluded 622 sessions / 15,913 assistant turns / 640 corrections; cross-check filtered Pi 182 sessions / 4,082 assistant turns / 159 corrections. Public-cohort Boucle exclusion removed only 11 sessions (1 `queue-operation`, 10 W10–W12 zero-tool), so this public cohort does not reproduce the private corpus's massive W10–W12 contamination. Current middens HSMM: baseline 3.55×, Boucle-excluded 5.61×, cross-check 6.04×. Legacy HSMM on fixed raw symlink cohorts with its own filters/sampling: baseline 24.72×, Boucle-excluded 41.32×, cross-check 25.56×. Conclusion: direction replicated, magnitude implementation-sensitive; keep HSMM downgraded/provisional rather than citing a single 24.6×-style headline.

**Independent public HF candidate-dataset HSMM summaries are also complete** (2026-05-25), after user correctly pointed out that “do not pool candidates into one headline” does not mean “do not analyze them.” Runner: `scripts/run_public_hf_independent_hsmm.py`. Gitignored artifacts: `experiments/hsmm-public-hf-independent/`. Sanitized write-up: `docs/solutions/methodology/public-hf-independent-dataset-hsmm-20260525.md`. Covered all user-shared seed datasets, all `other=pi-share-hf` candidates observed 2026-05-23, and all `search=claude code` candidates observed 2026-05-23. Results: 19 datasets completed current-middens HSMM independently, 11 were below HSMM guardrails, 1 was model-unstable, and 6 need additional parser/Parquet normalizer support. Completed examples: `badlogicgames/pi-mono` 5.61×, `thomasmustier/pi-for-excel-sessions` 7.86×, `thomasmustier/pi-extensions-sessions` 6.17×, `aaaaliou/pi-mono` 1.44×, `armand0e/kimi-k2.6-claude-code-traces` 1.89×. Several `*-pi-mono` repos are duplicate-shaped with identical aggregate counts/lift; keep them separate in the table, but do not count them as independent replication without deduplication. This reinforces the status: direction often appears; magnitude varies by dataset family.

**HF public corpus analysis CI is implemented** (2026-05-25; split smoke added 2026-05-26). Registry: `docs/corpora/public-hf-analysis-corpora.json`. Helpers: `scripts/hf_corpus_matrix.py`, `scripts/materialize_hf_analysis_corpus.py`, `scripts/build_hf_corpus_registry_dataset.py`, `scripts/publish_hf_corpus_registry.py`, and `scripts/fetch_hf_corpus_registry.py`. Workflow: `.github/workflows/hf-corpus-analysis.yml`. Methodology note: `docs/solutions/methodology/hf-corpus-analysis-ci-20260525.md`. Todo: `todos/hf-public-corpus-analysis-ci.md` done. CI tiers: PRs run smoke (`agent-sessions-list-mixed`); weekly schedule runs full; manual dispatch supports `tier={smoke,representative,full}`, `corpus=<id>|all`, and optional `registry_repo`/`registry_revision`. Scheduled runs can use repo variables `HF_CORPUS_REGISTRY_REPO` and `HF_CORPUS_REGISTRY_REVISION` to fetch `corpora.json` from a published HF dataset. Each matrix job builds middens, materializes the pinned HF JSONL corpus, runs `middens analyze --all --timeout 1800 --force`, exports with `middens export --no-interpretation`, validates the manifest has 23 technique entries, then runs a lightweight public-data split regression (`middens analyze --split --no-python`) and validates `interactive`/`subagent`/`autonomous` stratum manifests. No LLM interpretation layer is invoked. Local smoke validation passed: 7 sessions parsed, 23/23 techniques completed, export succeeded; split smoke on the same HF corpus produced 5 interactive, 2 subagent, 0 autonomous. Publishing the registry to HF is blocked only by local auth: no HF token was present, and `scripts/publish_hf_corpus_registry.py --repo-id Lightless-Labs/third-thoughts-public-corpora` failed early with the expected token-specific message. User-shared `SALT-NLP/SWE-chat` is recorded in the registry as disabled candidate `salt-nlp-swe-chat` pinned at `f66cca95b14caaa4177f7ed5eaa424608dadcffa`; it has ~5,850 transcript JSONL files plus Parquet tables, but is gated (`gated=auto`) and unauthenticated transcript download returns 401, so enable only after a durable HF secrets/trigger strategy (`todos/swe-chat-hf-corpus-enable.md`). A one-off user-provided-token smoke on 2026-05-26 confirmed gated access, downloaded three transcript JSONL files, and `middens analyze --split --no-python` parsed all three as subagent sessions (0 interactive / 3 subagent / 0 autonomous); temporary raw/cache/output artifacts were deleted. README line 379 says user prompts and assistant text responses were redacted with Microsoft Presidio plus TruffleHog; useful provenance, but still audit thinking/tool/code fields before treating derived artifacts as privacy-safe. A metadata-only full per-user aggregate pass is complete via `scripts/analyze_swe_chat_per_user.py` and documented in `docs/solutions/methodology/swe-chat-per-user-analysis-20260526.md`; local gitignored artifacts live under `experiments/swe-chat-per-user/`. Result: 5,851 sessions, 190 user groups, 1,943 sessions with missing `user_id`, 201 repos, 180 owners. Full 23-technique per-user middens battery was then attempted with `scripts/run_swe_chat_per_user_middens.py` for currently supported/likely-supported agents (`Claude Code`, `claude-code`, `Codex`). Dataset-specific SWE-chat mechanics now live in `scripts/hf_dataset_adapters.py` (`SweChatAdapter`): metadata tables are Parquet, raw transcripts live at canonical HF paths `transcripts/{session_id}.jsonl`, and `sessions.transcript_path` is provenance/fallback rather than generic truth. Local gitignored artifacts live under `experiments/swe-chat-per-user-middens/`. Result: 175 selected user groups / 5,066 sessions; 165 groups / 4,999 selected sessions completed with 23/23 technique entries and zero technique errors. Ten groups failed: seven no supported parser matched, three storage PII column-name blocklist failures from MCP tool names containing `content`. Raw gated transcript materialization/cache under `.tmp/` was deleted after the batch.

**Public HF 23-technique full-battery findings are documented** (2026-05-26) after user pointed out that we have 23 tools, not just HSMM. Write-up: `docs/solutions/methodology/public-hf-23-technique-analysis-findings-20260526.md`. Local/gitignored artifacts: `.tmp/hf-full/`, `.tmp/middens-full/`, `.tmp/xdg-full/`, `.tmp/reports-full/`, plus smoke artifacts. Full `middens analyze --all` and `export --no-interpretation` passed on all CI-selected corpora: `agent-sessions-list-mixed` (7 sessions), `badlogicgames-pi-mono` (626), `thomasmustier-pi-for-excel` (161), `aaaaliou-pi-mono` (145), and `kimi-claude-code-traces-jsonl` (36). Findings beyond HSMM: public Pi corpora show high thinking risk suppression (91–95% in the selected runs), MVT compliance is 0% across all selected corpora, corrections front-load on larger Pi corpora, Kimi/Claude-style traces differ sharply (low correction rate, higher tool entropy, ENA top code `SELF_CORRECT`), Granger relationships vary by corpus, change-point detection finds zero shifts, and cross-project graph remains mostly unusable on these selected corpora. Registry expected JSONL counts were corrected to materialized transcript counts (excluding dataset-side manifest JSONL): badlogicgames 626, pi-for-excel 161, aaaaliou 145.

**Autonomous session stratum Phase 1 is code-complete; regression coverage now relies on public HF corpora** (2026-05-26). `SessionType::Autonomous` exists; the session classifier now uses precedence `Subagent` (explicit parser/path/tool-result signal) → `Interactive` (any `Human*`, including `HumanQuestion`) → `Autonomous` (≥1 user message and zero `Human*`) → `Unknown`. `middens analyze --split` now writes `interactive/`, `subagent/`, and `autonomous/` strata and reports all three counts. Validation: `cd middens && cargo test` → 380/380 scenarios, 2103/2103 steps; `cd middens && cargo build --release --locked` → pass; local HF split smoke on `agent-sessions-list-mixed` → 5 interactive, 2 subagent, 0 autonomous. Old private-corpus rerun/addendum remains blocked because local `corpus-split/` is a stale absolute-symlink split over Claude Code live storage: after correcting the old repo path prefix, only 46/2,594 interactive and 4,757/5,348 subagent targets still exist, consistent with Claude Code pruning old session files. Use HF datasets for ongoing tests rather than this stale split. Todo `todos/autonomous-session-stratum.md` is updated accordingly.

Distribution Step D remains complete: source-built `middens 0.0.1-beta.3` and Homebrew-installed `middens 0.0.1-beta.3` were run against the same 10-session public `badlogicgames/pi-mono` slice with `--all`; manifests/parquet/notebook structure matched after normalizing expected run IDs/timestamps and allowing tiny floating-point tolerance. Apple Silicon Homebrew was refreshed again for beta.4 with `brew reinstall`, `middens --version`, `brew test`, and `brew audit --strict --online`. The default install pulls `uv` as a recommended dependency; `--without-uv` was validated previously for beta.0.

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
| Test suite | **380/380 passing** | 2103 steps (`cd middens && cargo test`, after autonomous stratum Phase 1 code, 2026-05-26) |

---

## Open work (prioritized)

### P0 — Distribution (remaining blockers)

Remaining blocking steps. See individual `todos/distribution-*.md` for detail.

1. ~~**Step A — e2e verb**~~ **DONE** (`middens run`, commit `7aea3c6`). Chains analyze → interpret → export. `--model` optional; omit to skip interpret. Hard-fails on interpret error.

2. ~~**Step B — release workflow**~~ **DONE** (commit `49d896f`; matrix narrowed 2026-04-18 after Intel-Mac runner starvation on first tag cut). `.github/workflows/release.yml` triggers on `v*` tag. Native GH-hosted runners (no `cross`): `macos-14` (darwin-arm64), `ubuntu-latest` (linux-x86_64), `ubuntu-24.04-arm` (linux-arm64, free for public repos). `x86_64-apple-darwin` dropped — `macos-13` is queue-starved on free public repos and the first tag cut sat 9h waiting for a runner. Tarballs + per-artifact SHA256 + combined SHA256SUMS via `softprops/action-gh-release@v2`. Windows left as future stretch. Rationale + failure-mode log at `docs/solutions/best-practices/github-actions-rust-cross-platform-release-matrix-20260417.md`. Follow-up todos from the pre-tag codex review: `todos/release-workflow-pin-actions-and-toolchain.md` (P2), `todos/release-workflow-orphan-sha256-sidecars.md` (P3).

3. ~~**Step C — Homebrew tap**~~ **DONE** (2026-04-27; refreshed 2026-05-23): tap repo created at <https://github.com/Lightless-Labs/homebrew-tap>. Formula installs `v0.0.1-beta.4` release binaries for Apple Silicon macOS, x86_64 Linux, and arm64 Linux. `uv` is `recommended`, not required; `--without-uv` and default install paths were validated for beta.0, beta.3 was validated locally on Apple Silicon, and beta.4 was validated with default dependencies plus `brew test` and `brew audit --strict --online`. Tap naming decision: generic `homebrew-tap`, yielding `brew install lightless-labs/tap/middens`. (`todos/distribution-homebrew-tap.md`)

4. ~~**Step D — two validation runs**~~ **DONE** (2026-05-20): source-built run vs brew-installed run completed on the same 10-session public Pi coding-agent Hugging Face slice. Both ran 23 techniques; manifests/parquet/notebook structure matched after expected run-id/timestamp normalization and tiny float tolerance. Validation found and fixed two nondeterminism bugs before the final beta.3/tap pass. (`todos/distribution-validation-runs.md`)

5. ~~**Step E — GitHub Pages landing page**~~ **INITIAL CUT SHIPPED** (2026-04-18). Site live at <https://lightless-labs.github.io/third-thoughts/>. Homebrew install story refreshed 2026-04-27. Remaining non-blocking site follow-ups live in `todos/distribution-github-pages.md` (embedded validation reports, contribution surface, second copy review, roadmap teaser).

### P0 — Next distribution/data-retention work

- ~~**Codex 5.5 xhigh review of archive plugins via Pi**~~ **DONE** (2026-05-21): review output saved at `docs/reviews/2026-05-21-archive-plugins-codex-55-xhigh-pi.md`; confirmed P1/P2 findings fixed, and follow-up regression tests completed in `integrations/tests/archive-plugin-regression.test.mjs`. (`todos/archive-plugins-codex-55-xhigh-review.md`, `todos/archive-plugin-regression-tests.md`)
- ~~**Session-log backup/archive**~~ **DONE** (2026-05-21, commit `51ef8b6`): `middens archive` discovers supported local session stores, copies raw JSONL logs into a user-controlled content-addressed archive, deduplicates by SHA-256, records object/observation manifest entries, supports dry-run, and never mutates source logs. Built via NLSpec + red/green adversarial process because raw private data plumbing should be boring and a little paranoid. (`todos/session-log-backup-archive.md`)

### P1 — Archive automation improvements

- ~~**Pi extension for automatic archives**~~ **DONE** (2026-05-21): package lives at `integrations/pi/middens-archive/`; registers `/middens-archive-now` and `/middens-archive-status`; uses explicit `MIDDENS_ARCHIVE_ROOT`; debounces periodic/shutdown runs and blocks overlap; now uses a bundled self-contained archiver rather than shelling out to `middens`. Typechecked and smoke-tested with temp `HOME` fixture. (`todos/archive-pi-extension-auto-backup.md`)
- ~~**Claude Code hook/plugin for automatic archives**~~ **DONE** (2026-05-21): package lives at `integrations/claude-code/middens-archive/`; Claude marketplace at `integrations/claude-code/.claude-plugin/marketplace.json`; hooks on `SessionStart`, `UserPromptSubmit`, and `Stop`; manual `/middens-archive-now`; bundled archiver, explicit `MIDDENS_ARCHIVE_ROOT`. (`todos/archive-claude-code-plugin-auto-backup.md`)
- ~~**Codex hook/plugin for automatic archives**~~ **DONE** (2026-05-21): package lives at `integrations/codex/middens-archive/`; Codex local marketplace at `integrations/codex/.agents/plugins/marketplace.json`; lifecycle hooks plus `middens-archive-now` / `middens-archive-status` skills; bundled archiver, explicit `MIDDENS_ARCHIVE_ROOT`. (`todos/archive-codex-plugin-auto-backup.md`)

### P1 — Research follow-ups

- ~~**Fixed public HF cohort for HSMM replication**~~ **DONE** (2026-05-24): `scripts/build_public_hf_hsmm_cohort.py` materializes pinned public HF datasets under gitignored `experiments/hsmm-public-hf-fixed/`, records SHA-256/object metadata/normalization status/contamination flags/inclusion flags, and writes normalized `Session[]` plus legacy symlink cohorts. Sanitized write-up: `docs/solutions/methodology/fixed-public-hf-hsmm-rerun-20260524.md`. (`todos/fixed-public-hf-agent-session-cohort.md`)
- ~~**HSMM re-run with Boucle excluded**~~ **DONE** (2026-05-24): Current middens HSMM on fixed public cohort: baseline 3.55×, Boucle-excluded 5.61×, cross-check 6.04×. Legacy HSMM on fixed raw symlink cohorts with legacy sampling/filtering: baseline 24.72×, Boucle-excluded 41.32×, cross-check 25.56×. Direction replicates; magnitude is implementation-sensitive, so the finding remains downgraded/provisional. (`todos/hsmm-rerun-boucle-excluded.md`)
- **Autonomous session stratum**: Phase 1 code is complete (`SessionType::Autonomous`, classifier, three-way `--split`) but the real-corpus rerun/addendum is pending because local `corpus-split/` symlinks are broken. Full plan at `todos/autonomous-session-stratum.md`. Required for the 4-axis compound scoping rule. Phase 2: run 23-technique battery on the new stratum after defensible real-corpus materialization.
- **Multilingual remediation**: implement language detection + refusal on `thinking-divergence`, `correction-rate` lexical layer, `user_signal_analysis`. Adds `whatlang` (or equivalent). Populates `Session::language`. Then re-run risk-suppression replications under `language=en` gate. (`todos/multilingual-text-techniques.md`)
- **Public HF Parquet trace normalizers**: add schema-aware, streaming-safe normalizers so public Claude Code Parquet trace datasets can join the full `middens analyze --all` CI path. (`todos/public-hf-parquet-trace-normalizers.md`)

### P2 — Tech debt

- **Publish public HF corpus registry**: optional, token-gated step to publish the repo-local corpus registry as a Hugging Face dataset and configure CI to fetch it via repo variables/manual inputs. (`todos/public-hf-registry-publish.md`)
- **Deduplicate public HF corpora**: quantify duplicate/subset relationships among duplicate-shaped `*-pi-mono` datasets before treating them as independent replication evidence. (`todos/public-hf-corpus-deduplication.md`)
- **CLI version at message level**: `Message::version` + `SessionMetadata::versions: Vec<String>` — enables corpus stratification by Claude Code CLI version. (`todos/message-level-version-field.md`)
- **Frustration classifier recalibration**: 90% of user signals pile up at intensity 2. Needs rescaling or model change. (`user_signal_analysis.py`)
- Deferred PR review items: `todos/batch4-coderabbit-deferred.md`, `todos/batch3-coderabbit-deferred.md`
- Todos filed but not started: `fingerprint-technique-retrofit.md`, `corpus-timeline-deletion.md`, `batches-1-2-pii-and-type-audit.md`, `interpret-parser-strictness.md`, `interpret-export-split-composition.md`

### P2 — Pre-release review follow-ups (filed 2026-04-18, post v0.0.1-beta.0 tag)

From the codex xhigh pre-tag review (two rounds). None were beta-tag blockers; the five round-1 blockers and two round-2 blockers were fixed in-session. Remaining should-fix items:

- `todos/middens-hide-unimplemented-subcommands.md` — `report`/`fingerprint` print `[not yet implemented]`; hide or implement
- `todos/middens-export-dir-mismatch-validation.md` — `export --analysis-dir A --interpretation-dir B` silently accepts mismatched dirs
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
| HSMM pre-failure/pre-correction state | **Provisional — direction replicated, magnitude unstable** (2026-05-24 fixed public HF re-run) | Current middens: 3.55× baseline → 5.61× Boucle-excluded; legacy: 24.72× → 41.32× under its own filters/sampling. Do not cite a single 24.6×-style headline. `docs/solutions/methodology/fixed-public-hf-hsmm-rerun-20260524.md` |
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
| `main` | Local `main` includes session archive work, archive automation plugins, beta.4 release docs, fixed public HF HSMM replication, independent public-HF HSMM summaries, HF corpus analysis CI, optional HF registry publication tooling, and public-HF 23-technique findings. `origin/main` status not rechecked after local commits `df8838e`..`004b868`; tag `v0.0.1-beta.4` is pushed and released. |

No open PRs. No feature branches.

### Local working tree

- Tracked working-tree changes currently expected if this handoff is read mid-session: SWE-chat adapter refactor in `scripts/hf_dataset_adapters.py`, `scripts/run_swe_chat_per_user_middens.py`, `scripts/analyze_swe_chat_per_user.py`, `docs/solutions/methodology/swe-chat-per-user-analysis-20260526.md`, and this handoff. Commit and push once reviewed.
- `www` branch landing-page Linux tarball copy was pushed as `0188acc`; mobile code-block wrapping fix was pushed as `f01c672`.
- Tap formula was updated to `v0.0.1-beta.4` and pushed to `Lightless-Labs/homebrew-tap` as `7d488f8`.
- Untracked analysis output: `middens-results/` (local run artifacts; do not commit blindly)
- Gitignored fixed-cohort/public-HF artifacts: `experiments/hsmm-public-hf-fixed/`, `experiments/hsmm-public-hf-independent/`, `.tmp/hf-*`, `.tmp/middens-*`, `.tmp/xdg-*`, `.tmp/reports-*`. Do not force-add raw/normalized transcript artifacts.
- Homebrew side effect: `middens` is currently installed from `lightless-labs/tap` at `0.0.1-beta.4`; `uv` is installed because the default install path was validated.

---

## Test suite

**380/380 Cucumber scenarios, 2103 steps — all passing.**

Last Rust run: 2026-05-26, after autonomous stratum Phase 1 code.

Run: `cd middens && cargo test`

Archive plugin validation (2026-05-23): `cd integrations/pi/middens-archive && npm test` → 8/8 Node tests; `cd integrations/pi/middens-archive && npm run check`; bundled archiver fixture smokes for `pi-coding-agent`, `claude-code`, and `codex`; Pi `pi -e ./integrations/pi/middens-archive -p /middens-archive-status` with temp `HOME` and unset root; Pi temp-`HOME` `/middens-archive-now` smoke without `middens` on `PATH`; temp `PI_CODING_AGENT_DIR` local package install smoke for both subpackage and repo-root manifests; `claude plugin validate integrations/claude-code/middens-archive`; `claude plugin validate integrations/claude-code`; `codex plugin marketplace add ./integrations/codex --enable plugin_hooks` with temp `HOME`; Claude/Codex hook wrapper fixture smokes.

Release validation (2026-05-23, beta.4): `cd middens && cargo test` → 375/375 scenarios, 2081/2081 steps plus doctest; `cd middens && cargo build --release --locked`; `cd integrations/pi/middens-archive && npm test`; `cd integrations/pi/middens-archive && npm run check`; GitHub release workflow `26325365657` success; Homebrew `brew reinstall lightless-labs/tap/middens`, `middens --version`, `brew test lightless-labs/tap/middens`, and `brew audit --strict --online lightless-labs/tap/middens` all passed.

Fixed public HF HSMM validation (2026-05-24): `python3 -m py_compile scripts/build_public_hf_hsmm_cohort.py`; `python3 scripts/build_public_hf_hsmm_cohort.py --force`; current middens HSMM direct runs on `public_hf_baseline_fixed`, `public_hf_boucle_excluded_fixed`, and `crosscheck_filtered_pi`; legacy `scripts/hsmm_behavioral_states.py` runs on the three fixed raw symlink cohorts.

Independent public HF candidate validation (2026-05-25): `python3 -m py_compile scripts/run_public_hf_independent_hsmm.py`; `python3 scripts/run_public_hf_independent_hsmm.py --force` completed over 36 pinned public candidate datasets. HF rate limits triggered retries but run completed.

HF public corpus analysis CI validation (2026-05-25; split smoke 2026-05-26): `python3 -m py_compile scripts/hf_corpus_matrix.py scripts/materialize_hf_analysis_corpus.py`; `python3 scripts/hf_corpus_matrix.py --tier smoke`; `python3 scripts/materialize_hf_analysis_corpus.py --corpus agent-sessions-list-mixed --output .tmp/hf-ci-smoke --cache-dir .tmp/hf-cache-smoke --force`; `XDG_DATA_HOME=$PWD/.tmp/xdg-ci-smoke ./middens/target/release/middens analyze .tmp/hf-ci-smoke --all --timeout 1800 --force --output .tmp/middens-ci-smoke`; export with `--no-interpretation`; manifest assertion `len(techniques) == 23`. Split smoke: `python3 scripts/materialize_hf_analysis_corpus.py --corpus agent-sessions-list-mixed --output .tmp/hf-split-smoke --cache-dir .tmp/hf-cache-smoke --force`; `XDG_DATA_HOME=$PWD/.tmp/xdg-split-smoke ./middens/target/release/middens analyze .tmp/hf-split-smoke --split --no-python --output .tmp/middens-split-smoke`; validated `interactive`/`subagent`/`autonomous` split outputs and stratum manifests (5/2/0 sessions). Registry publication tooling validation: `python3 -m py_compile scripts/build_hf_corpus_registry_dataset.py scripts/fetch_hf_corpus_registry.py scripts/publish_hf_corpus_registry.py`; `python3 scripts/build_hf_corpus_registry_dataset.py --output .tmp/hf-registry-dataset-test`; publish script fails clearly without HF token.

Public HF full-battery validation (2026-05-26): materialized and ran `middens analyze --all --timeout 1800 --force` + `export --no-interpretation` for `badlogicgames-pi-mono`, `thomasmustier-pi-for-excel`, `aaaaliou-pi-mono`, and `kimi-claude-code-traces-jsonl`; smoke corpus had already passed. All selected corpora completed 23/23 techniques and exported notebooks.

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
