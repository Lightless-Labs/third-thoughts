---
title: "feat: Public repo prep + Middens CLI wiring & Phase 2 techniques"
type: feat
status: active
date: 2026-03-29
origin: docs/brainstorms/2026-03-20-middens-cli-requirements.md
---

# feat: Public repo prep + Middens CLI wiring & Phase 2 techniques

## Overview

Two parallel workstreams: (A) prepare the third-thoughts repo for public release on GitHub — .gitignore, path redaction, remote setup, initial push; (B) wire the middens CLI commands to the existing Phase 1 library and implement the Phase 2 Rust-native analytical techniques.

## Problem Frame

The third-thoughts repo has a solid Phase 1 library (49 tests, parsers, classifiers, corpus discovery) but: (1) it has no git remote and contains untracked files with private data (corpus, experiments, hardcoded paths) that must never reach GitHub; (2) all 6 CLI subcommands print stub messages despite the library being fully functional; (3) zero analytical techniques are implemented despite the `Technique` trait and result types being ready.

(see origin: `docs/brainstorms/2026-03-20-middens-cli-requirements.md`)

## Requirements Trace

- R-A1. Repository must be safe for public GitHub — no corpus data, no real usernames, no absolute paths to private directories
- R-A2. Git history must be clean (verified: only middens source + synthetic fixtures committed)
- R-A3. `.gitignore` must exclude corpus data, experiments, labeled datasets, build artifacts, and runtime files
- R-A4. Scripts and docs with hardcoded absolute user paths must be redacted to use relative paths or environment variables
- R-A5. Remote `git@github.com:Lightless-Labs/third-thoughts.git` added and initial push completed
- R-B1. `middens parse <file>` calls `parse_auto()` and outputs JSON (R14 from origin)
- R-B2. `middens freeze <path>` calls `create_manifest()` and writes JSON manifest (R12 from origin)
- R-B3. `middens list-techniques` shows available techniques with descriptions and Python requirements (R14 from origin)
- R-B4. Markov chain tool transition technique — transition matrix, self-loop rates, stationary distribution (R7 from origin)
- R-B5. Entropy rate + anomaly detection — sliding-window conditional entropy, mean +/- 2 sigma anomalies (R7)
- R-B6. Shannon/Simpson diversity indices — per-session tool diversity, species-area curve fitting (R7)
- R-B7. Burstiness coefficients — Barabasi B and memory M per event type (R7)
- R-B8. Correction rate metrics — per-session, per-project, maturity curve (R7)
- R-B9. Technique registry with `--techniques` flag filtering (R14)

## Scope Boundaries

- No Python bridge (Phase 4) — only Rust-native techniques
- No output engine beyond JSON serialization — markdown/Parquet/Vega-Lite output is Phase 3
- No `middens analyze` pipeline wiring — that requires techniques + output engine together (Phase 5)
- No `middens fingerprint` — requires implementing the fingerprint extraction stubs (separate work)
- No new parsers (Cursor, OpenCode, Gemini full) — tracked in `todos/additional-parsers.md`
- Scripts redaction is path-only — no content changes to analysis logic

## Context & Research

### Relevant Code and Patterns

- `middens/src/techniques/mod.rs` — `Technique` trait with `name()`, `description()`, `requires_python()`, `is_essential()`, `run(&[Session])` methods. `TechniqueResult` with `findings`, `tables`, `figures` fields
- `middens/src/session.rs` — `Session` type with `tool_sequence()`, `correction_count()`, `thinking_count()`, `total_tool_calls()` helpers already implemented
- `middens/src/parser/auto_detect.rs` — `parse_auto(path)` returns `Result<Vec<Session>>`, handles detection + parsing + classification in one call
- `middens/src/corpus/manifest.rs` — `create_manifest(path, output)` already fully implemented with SHA-256 hashing
- `middens/src/corpus/discovery.rs` — `discover_sessions(path)` returns `Result<Vec<PathBuf>>`
- Test pattern: inline `#[cfg(test)] mod tests` with `tempfile::TempDir` for filesystem tests

### Institutional Learnings

- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — always stratify by session type
- `docs/solutions/patterns/risk-suppression-85-percent-constant-20260320.md` — 85.5% risk suppression is the most robust finding
- `docs/solutions/architecture/pluggable-parser-trait-pattern-20260320.md` — single-file trait implementation pattern

## Key Technical Decisions

- **Redact scripts with env vars, not relative paths**: Scripts use `MIDDENS_CORPUS` and `MIDDENS_OUTPUT` env vars with sensible defaults (`corpus/` and `experiments/`). This is more portable than relative paths and matches how the CLI works (`middens analyze <path>`)
- **Technique registry as a function, not a global**: `all_techniques() -> Vec<Box<dyn Technique>>` mirrors the existing `all_parsers()` pattern in `parser/mod.rs`
- **JSON output only for `parse` command**: The `--format` flag accepts `json` (default) and `json-pretty`. No markdown/yaml output for the debug parse command — that's the output engine's job
- **Techniques return TechniqueResult, CLI serializes**: Each technique produces a `TechniqueResult`; the CLI command handles serialization. This keeps techniques pure and testable
- **.gitignore over .git/info/exclude**: Public repo needs the ignore rules to be visible and version-controlled

## Open Questions

### Resolved During Planning

- **Should experiments/ be committed?**: No — outputs contain real usernames and project names throughout. The scripts that generate them can be committed (after redaction); the outputs stay local
- **Should docs/reviews/ be partially committed?**: Yes — 4 of 7 review files are clean (claude-001-003, claude-010-012, gemini-007-009, gemini-016-018). The 3 with hardcoded paths (codex-004-006, codex-013-015, claude-019-022) should be excluded or redacted
- **Is git history clean?**: Yes — verified. Only `middens/` source code and synthetic test fixtures in all 3 commits

### Deferred to Implementation

- Exact env var names for scripts — implementation will audit each script's path usage
- Whether `docs/reviews/` files with paths are worth redacting vs just excluding — depends on how many path references each has

## Implementation Units

- [ ] **Unit 1: Create .gitignore**

**Goal:** Establish what gets excluded from the public repo

**Requirements:** R-A1, R-A3

**Dependencies:** None

**Files:**
- Create: `.gitignore`
- Test: Manual verification via `git status`

**Approach:**
- Exclude: `corpus*/`, `experiments/`, `data/labeled-messages.json`, `docs/materials/`, `nohup.out`, `middens/target/`, `*.pkl`, `*.pyc`, `__pycache__/`
- Include: `data/validation-results.json` (aggregate metrics only)
- Follow standard Rust .gitignore patterns for `target/`

**Test scenarios:**
- Happy path: `git status` no longer shows corpus directories as untracked
- Edge case: `data/` dir partially tracked — `validation-results.json` included, `labeled-messages.json` excluded

**Verification:**
- `git status` shows only files intended for commit as untracked

---

- [ ] **Unit 2: Redact hardcoded paths in scripts/**

**Goal:** Replace all hardcoded absolute user paths and username references with environment variables

**Requirements:** R-A4

**Dependencies:** None (parallel with Unit 1)

**Files:**
- Modify: All 26 files in `scripts/` that contain hardcoded paths
- Test: `grep -r '/Users/' scripts/` returns zero matches

**Approach:**
- Replace hardcoded corpus paths with `os.environ.get("MIDDENS_CORPUS", "corpus/")`
- Replace hardcoded output paths with `os.environ.get("MIDDENS_OUTPUT", "experiments/")`
- Replace username-stripping logic with a generic path-component anonymizer (strip all `-Users-*-` prefixes)
- Do not change analysis logic — path handling only

**Test scenarios:**
- Happy path: Scripts run without error when `MIDDENS_CORPUS` and `MIDDENS_OUTPUT` are set
- Edge case: Scripts fall back to default paths when env vars are unset
- Edge case: Username anonymizer handles arbitrary usernames, not just the three hardcoded ones

**Verification:**
- `grep -rn '/Users/' scripts/` returns zero matches

---

- [ ] **Unit 3: Redact paths in docs/**

**Goal:** Remove stray absolute paths from documentation files

**Requirements:** R-A4

**Dependencies:** None (parallel with Units 1-2)

**Files:**
- Modify: ~6-8 files in `docs/` with stray absolute user paths (reports, plans, brainstorms, sawdust reports, synthesis docs)
- Exclude from repo: `docs/materials/` (zip files of raw sessions), `docs/reviews/codex-004-006.md`, `docs/reviews/codex-013-015.md`, `docs/reviews/claude-019-022.md`
- Test: `grep -r '/Users/' docs/` returns zero matches after redaction

**Approach:**
- Replace absolute paths with relative paths or generic placeholders (e.g., `~/.claude/projects/`)
- For review files with too many path references: add to `.gitignore` rather than redacting

**Test scenarios:**
- Happy path: All committed docs files contain no absolute paths to private directories

**Verification:**
- `grep -rn '/Users/' docs/` returns zero matches (excluding gitignored files)

---

- [ ] **Unit 4: Add remote, commit, and push**

**Goal:** Get the public repo live on GitHub

**Requirements:** R-A5

**Dependencies:** Units 1-3

**Files:**
- Modify: git config (remote)
- Stage: `.gitignore`, `CLAUDE.md`, `docs/` (redacted), `scripts/` (redacted), `todos/`, `data/validation-results.json`

**Approach:**
- `export SSH_AUTH_SOCK=~/.ssh/agent.sock` (per Lightless Labs convention)
- `git remote add origin git@github.com:Lightless-Labs/third-thoughts.git`
- Stage all public-safe files, commit, push
- Verify on GitHub that no private data is visible

**Test scenarios:**
- Happy path: `git push` succeeds, GitHub repo shows only safe files
- Error path: Push fails due to auth — verify SSH_AUTH_SOCK is set

**Verification:**
- Remote repo accessible at github.com/Lightless-Labs/third-thoughts
- No files matching `.gitignore` patterns present in remote

---

- [ ] **Unit 5: Wire `middens parse` command**

**Goal:** Connect the `parse` subcommand to the existing `parse_auto()` library function

**Requirements:** R-B1

**Dependencies:** None (parallel with Units 1-4)

**Files:**
- Modify: `middens/src/main.rs`
- Test: `middens/src/main.rs` (inline tests or integration test)

**Approach:**
- Call `middens::parser::auto_detect::parse_auto(&file)`
- Serialize result as JSON to stdout (pretty-print by default for human readability)
- Error handling: report parse failures to stderr, exit with non-zero code
- The `--format` flag already exists in the CLI args — wire it to control pretty vs compact JSON

**Patterns to follow:**
- `parse_auto()` already handles detection, parsing, and classification in one call
- Follow the existing `eprintln!` pattern for status messages to stderr

**Test scenarios:**
- Happy path: `middens parse tests/fixtures/claude_code_sample.jsonl` outputs valid JSON with parsed session data
- Happy path: Output includes classified messages and session type
- Error path: `middens parse nonexistent.jsonl` prints error to stderr and exits non-zero
- Edge case: `middens parse` on an unrecognized format outputs empty JSON array

**Verification:**
- `cargo run -- parse middens/tests/fixtures/claude_code_sample.jsonl | jq .` succeeds and shows structured session data

---

- [ ] **Unit 6: Wire `middens freeze` command**

**Goal:** Connect the `freeze` subcommand to the existing `create_manifest()` function

**Requirements:** R-B2

**Dependencies:** None (parallel with Unit 5)

**Files:**
- Modify: `middens/src/main.rs`

**Approach:**
- Call `middens::corpus::manifest::create_manifest(&path, &output)`
- The function already handles walking, hashing, and JSON output
- Status messages already printed to stderr by the library function

**Test scenarios:**
- Happy path: `middens freeze <dir> -o manifest.json` creates a JSON manifest with SHA-256 hashes
- Error path: `middens freeze /nonexistent` reports error gracefully

**Verification:**
- `cargo run -- freeze middens/tests/fixtures/ -o /tmp/test-manifest.json && jq '.entries | length' /tmp/test-manifest.json` shows correct entry count

---

- [ ] **Unit 7: Implement technique registry and wire `middens list-techniques`**

**Goal:** Create the technique registry and connect the `list-techniques` command

**Requirements:** R-B3, R-B9

**Dependencies:** None (but naturally comes before technique implementations for testing)

**Files:**
- Modify: `middens/src/techniques/mod.rs` — add `all_techniques()` function
- Modify: `middens/src/main.rs` — wire `ListTechniques` command
- Test: inline tests in `techniques/mod.rs`

**Approach:**
- `pub fn all_techniques() -> Vec<Box<dyn Technique>>` returns all registered techniques, mirroring `parser::all_parsers()`
- `list-techniques` iterates and prints name, description, essential/optional, requires_python
- `--essential` flag filters to essential-only
- Start with an empty registry, techniques register themselves as they're implemented in subsequent units
- Tabular output to stdout: `NAME | ESSENTIAL | PYTHON | DESCRIPTION`

**Patterns to follow:**
- `parser/mod.rs::all_parsers()` — same registry pattern

**Test scenarios:**
- Happy path: `list-techniques` outputs a formatted table of all registered techniques
- Happy path: `list-techniques --essential` shows only essential techniques
- Edge case: Registry starts empty, returns empty table gracefully

**Verification:**
- `cargo run -- list-techniques` prints a table (initially empty, populates as techniques are added)

---

- [ ] **Unit 8: Implement Markov chain tool transitions technique**

**Goal:** Compute tool-to-tool transition probabilities, self-loop rates, and stationary distribution

**Requirements:** R-B4

**Dependencies:** Unit 7 (registry exists to register into)

**Files:**
- Create: `middens/src/techniques/markov.rs`
- Modify: `middens/src/techniques/mod.rs` — register `MarkovChain`
- Test: inline tests in `markov.rs`

**Approach:**
- Use `session.tool_sequence()` to get ordered tool names
- Build NxN transition count matrix from bigrams
- Normalize rows to get transition probabilities
- Self-loop rate = diagonal entries
- Stationary distribution via power iteration (simple, no external deps)
- Findings: top-5 transitions, self-loop rates per tool, most/least common entry tools
- DataTable: full transition matrix as rows

**Test scenarios:**
- Happy path: Known sequence `[Read, Edit, Read, Bash]` produces correct transition matrix
- Happy path: Self-loop rate for a tool that always follows itself is 1.0
- Edge case: Session with zero or one tool call returns empty/trivial result
- Edge case: Single-tool session (all Bash) has 1.0 self-loop, trivial stationary distribution
- Integration: Registered in `all_techniques()` and appears in `list-techniques` output

**Verification:**
- `cargo test` passes for markov module
- Technique appears in `middens list-techniques`

---

- [ ] **Unit 9: Implement entropy rate + anomaly detection technique**

**Goal:** Compute sliding-window conditional entropy of tool sequences and flag anomalous regions

**Requirements:** R-B5

**Dependencies:** Unit 7

**Files:**
- Create: `middens/src/techniques/entropy.rs`
- Modify: `middens/src/techniques/mod.rs` — register `EntropyRate`
- Test: inline tests in `entropy.rs`

**Approach:**
- Sliding window (default 20 events) over tool sequences
- Conditional entropy: H(X_t | X_{t-1}) using observed bigram frequencies within window
- Per-session mean and std dev; flag windows > 2 sigma above or below mean
- Low-entropy anomalies = behavioral rigidity (the 3.7:1 ratio from the research)
- High-entropy anomalies = behavioral chaos
- Findings: mean entropy, anomaly count, low-vs-high ratio
- DataTable: per-window entropy values

**Test scenarios:**
- Happy path: Perfectly random sequence has high entropy; perfectly periodic sequence has zero entropy
- Happy path: A sequence with an anomalous rigid block flags the correct window
- Edge case: Session shorter than window size returns single-window result
- Edge case: Session with single tool type has zero entropy everywhere

**Verification:**
- `cargo test` passes for entropy module

---

- [ ] **Unit 10: Implement Shannon/Simpson diversity indices technique**

**Goal:** Compute tool usage diversity per session and fit species-area relationship

**Requirements:** R-B6

**Dependencies:** Unit 7

**Files:**
- Create: `middens/src/techniques/diversity.rs`
- Modify: `middens/src/techniques/mod.rs` — register `Diversity`
- Test: inline tests in `diversity.rs`

**Approach:**
- Shannon entropy H = -sum(p_i * ln(p_i)) over tool type proportions
- Simpson's diversity D = 1 - sum(p_i^2)
- Evenness E = H / ln(S) where S = number of unique tool types
- Species-area curve: fit S = c * A^z via log-log linear regression (A = session length in tool calls, S = unique tools). R^2 as goodness of fit
- Findings: mean/median Shannon, Simpson, evenness across sessions; species-area z exponent; monoculture sessions (evenness < 0.3)
- DataTable: per-session diversity metrics

**Test scenarios:**
- Happy path: Session using only Bash has Shannon=0, Simpson=0, evenness undefined (or 0)
- Happy path: Session with equal use of 4 tools has maximum Shannon=ln(4)
- Happy path: Species-area fit on synthetic data with known z recovers correct exponent
- Edge case: Empty session returns zeroes

**Verification:**
- `cargo test` passes for diversity module

---

- [ ] **Unit 11: Implement burstiness coefficients technique**

**Goal:** Compute Barabasi burstiness B and memory M for tool usage patterns

**Requirements:** R-B7

**Dependencies:** Unit 7

**Files:**
- Create: `middens/src/techniques/burstiness.rs`
- Modify: `middens/src/techniques/mod.rs` — register `Burstiness`
- Test: inline tests in `burstiness.rs`

**Approach:**
- For each tool type, compute inter-event intervals (number of other events between consecutive uses)
- B = (sigma - mu) / (sigma + mu) where sigma = std dev, mu = mean of intervals. B=1 maximally bursty, B=0 Poisson, B=-1 periodic
- Memory M = correlation between consecutive intervals: corr(tau_i, tau_{i+1})
- Per-tool and aggregate (weighted by frequency)
- Findings: burstiest tools, most periodic tools, aggregate B and M
- DataTable: per-tool B, M, mean interval, count

**Test scenarios:**
- Happy path: Perfectly periodic tool usage (every 3rd event) has B close to -1
- Happy path: All events clustered at start has B close to 1
- Edge case: Tool used only once — skip (insufficient data for interval computation)
- Edge case: Tool used exactly twice — B and M computable but M undefined (need 2+ intervals for correlation)

**Verification:**
- `cargo test` passes for burstiness module

---

- [ ] **Unit 12: Implement correction rate metrics technique**

**Goal:** Compute correction rates per session, per project, and maturity curves

**Requirements:** R-B8

**Dependencies:** Unit 7

**Files:**
- Create: `middens/src/techniques/correction_rate.rs`
- Modify: `middens/src/techniques/mod.rs` — register `CorrectionRate`
- Test: inline tests in `correction_rate.rs`

**Approach:**
- Per-session: corrections / total_user_messages ratio
- Per-project: aggregate across sessions sharing the same `metadata.project`
- Maturity curve: bin sessions by chronological order within a project, compute correction rate per bin to see if projects improve over time
- Session-position analysis: correction rate in first/middle/last third of session (the 7.24x hazard increase finding)
- Findings: overall correction rate, per-project rates, degradation ratio (last-third / first-third), projects with improving vs degrading trends
- DataTable: per-session and per-project correction rates

**Test scenarios:**
- Happy path: Session with 2 corrections in 10 user messages has rate 0.2
- Happy path: Corrections concentrated in last third produce degradation ratio > 1
- Edge case: Session with zero user messages — rate is 0 or undefined
- Edge case: All sessions in one project — project-level equals session-level
- Integration: Uses `MessageClassification::HumanCorrection` from the validated classifier

**Verification:**
- `cargo test` passes for correction_rate module

---

## System-Wide Impact

- **Parser/technique interface**: Techniques consume `&[Session]` — no changes needed to the parser layer
- **CLI argument parsing**: `list-techniques` needs wiring but args are already defined in clap. `parse` and `freeze` args are already defined
- **Error propagation**: All techniques return `Result<TechniqueResult>` — the future `analyze` pipeline will handle per-technique error reporting
- **No external API surfaces**: This is a local CLI tool with no network communication

## Risks & Dependencies

- **Script redaction may break scripts**: Changing path defaults could break scripts if run from unexpected directories. Mitigation: use env vars with fallback defaults that match the current repo layout
- **Technique accuracy**: Phase 2 techniques should produce results consistent with the Python scripts in `scripts/`. Mitigation: compare outputs on test fixtures where possible
- **SSH auth for push**: Requires `SSH_AUTH_SOCK=~/.ssh/agent.sock` to be set. Documented in Lightless Labs conventions

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-20-middens-cli-requirements.md](docs/brainstorms/2026-03-20-middens-cli-requirements.md)
- **Existing plan:** [docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md](docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md)
- **Roadmap:** [todos/next-moves.md](../../todos/next-moves.md), [todos/cli-tool-roadmap.md](../../todos/cli-tool-roadmap.md)
- Related code: `middens/src/parser/mod.rs::all_parsers()` (registry pattern), `middens/src/techniques/mod.rs` (trait definition)
