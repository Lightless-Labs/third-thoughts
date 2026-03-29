---
title: "feat: Middens CLI — AI Agent Session Log Analyzer"
type: feat
status: active
date: 2026-03-20
origin: docs/brainstorms/2026-03-20-middens-cli-requirements.md
---

# feat: Middens CLI — AI Agent Session Log Analyzer

## Overview

Middens is a Rust CLI tool that scans AI agent session logs (Claude Code, Codex CLI, Gemini CLI, Cursor, OpenClaw, OpenCode), runs 23+ analytical techniques from 14 academic disciplines against them, and produces research-grade findings. Named for archaeological garbage heaps that reveal more about civilizations than their monuments.

This plan covers v1: the headless analysis engine. Pull, build, run, get files.

## Problem Statement

The Third Thoughts research project proved that 23 analytical techniques can extract actionable findings from agent session transcripts (85.5% risk suppression, pre-failure state detection at 24.6x lift, agents under-exploring patches). These techniques currently exist as ad-hoc Python scripts with hardcoded paths and manual dependency management. No tool exists to make this analysis accessible.

(see origin: `docs/brainstorms/2026-03-20-middens-cli-requirements.md`)

## Proposed Solution

A Rust CLI binary with a pluggable parser architecture, automatic corpus discovery, session type classification, and a two-tier technique system: simple techniques in pure Rust, complex techniques via Python subprocess bridge managed by `uv`.

## Technical Approach

### Architecture

```
┌─────────────────────────────────────────────────┐
│                   middens CLI                    │
│                   (clap v4)                      │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ Corpus   │  │ Parser   │  │ Classifier    │ │
│  │ Discovery│→ │ Registry │→ │ (interactive/ │ │
│  │          │  │ (trait)  │  │  subagent)    │ │
│  └──────────┘  └──────────┘  └───────────────┘ │
│                      │                           │
│         ┌────────────┴────────────┐              │
│         ▼                         ▼              │
│  ┌─────────────┐         ┌──────────────┐       │
│  │ Rust        │         │ Python       │       │
│  │ Techniques  │         │ Bridge       │       │
│  │ (native)    │         │ (uv + subprocess)   │
│  └─────────────┘         └──────────────┘       │
│         │                         │              │
│         └────────────┬────────────┘              │
│                      ▼                           │
│  ┌──────────────────────────────────────┐       │
│  │ Output Engine                         │       │
│  │ (markdown + JSON + Parquet + VegaLite)│       │
│  └──────────────────────────────────────┘       │
│                                                  │
│  ┌──────────────────────────────────────┐       │
│  │ Environment Fingerprinter             │       │
│  │ (version, model, plugins, CLAUDE.md)  │       │
│  └──────────────────────────────────────┘       │
│                                                  │
│  ┌──────────────────────────────────────┐       │
│  │ Report Generator                      │       │
│  │ (cross-technique synthesis)           │       │
│  └──────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

### Build System

Start with Cargo, not Bazel. The monorepo's CLAUDE.md specifies Bazel, but zero Bazel infrastructure exists yet (`foundry_core` also uses Cargo). Pragmatic choice: build with Cargo now, migrate to Bazel when the monorepo matures. (Research finding: no WORKSPACE, BUILD.bazel, or .bazelrc files exist anywhere in the repo.)

### Crate Layout

```
third-thoughts/middens/
  Cargo.toml                    # edition = "2024", following foundry_core convention
  src/
    main.rs                     # CLI entry point (clap)
    lib.rs                      # Public API + re-exports
    session.rs                  # Unified Session type (parsed from any format)
    parser/
      mod.rs                    # SessionParser trait
      claude_code.rs            # Claude Code JSONL
      codex.rs                  # Codex CLI JSONL
      gemini.rs                 # Gemini CLI (directory-based, not JSONL)
      openclaw.rs               # OpenClaw JSONL
      cursor.rs                 # Cursor (schema TBD — not on this system)
      opencode.rs               # OpenCode (schema TBD — not on this system)
      auto_detect.rs            # Format detection from file structure/content
    classifier/
      mod.rs                    # Session type + message classifier
      correction.rs             # Correction classifier (port from Python, 98% accuracy)
      session_type.rs           # Interactive vs subagent detection
    fingerprint/
      mod.rs                    # Environment fingerprinting
      extract.rs                # Extract config signals from session metadata
      evolution.rs              # Track environment changes over time
    techniques/
      mod.rs                    # Technique trait + registry
      markov.rs                 # Tool transition matrices (Rust native)
      entropy.rs                # Entropy rate + anomaly detection (Rust native)
      diversity.rs              # Shannon/Simpson/species-area (Rust native)
      burstiness.rs             # Barabási burstiness + memory (Rust native)
      correction_rate.rs        # Correction rate metrics (Rust native)
    bridge/
      mod.rs                    # Python subprocess orchestration
      uv.rs                     # uv detection, installation, venv management
      technique.rs              # PythonTechnique wrapper (serializes data, calls script, parses results)
    corpus/
      mod.rs                    # Discovery, indexing, manifest
      discovery.rs              # Auto-find session logs across tools
      manifest.rs               # Freeze/snapshot support
    output/
      mod.rs                    # Output engine
      markdown.rs               # YAML-frontmatter markdown reports
      json.rs                   # JSON data files
      parquet.rs                # Parquet tabular data (arrow2 or polars)
      vegalite.rs               # Vega-Lite figure specs
      ascii.rs                  # ASCII sparklines for terminal
    report/
      mod.rs                    # Cross-technique synthesis report generator
  python/
    requirements.txt            # Python deps for complex techniques
    techniques/
      hsmm.py                  # Hidden Semi-Markov Model
      granger.py               # Granger causality
      survival.py              # Kaplan-Meier + Cox PH
      process_mining.py        # Inductive Miner (pm4py)
      smith_waterman.py        # Sequence alignment
      tpattern.py              # T-pattern detection
      prefixspan_mining.py     # PrefixSpan
      ena.py                   # Epistemic Network Analysis
      spc.py                   # SPC control charts
      ncd.py                   # NCD compression clustering
      epidemiology.py          # SIR convention propagation
      lag_sequential.py        # Lag sequential analysis
      foraging.py              # Information foraging
  tests/
    fixtures/                   # Sample JSONL files for each format
      claude_code_sample.jsonl
      codex_sample.jsonl
      openclaw_sample.jsonl
    parser_tests.rs
    classifier_tests.rs
    technique_tests.rs
    integration_tests.rs
```

### Implementation Phases

#### Phase 1: Foundation (parser + corpus + classifier)

The core pipeline: find files, parse them, classify them.

**Tasks:**
- [ ] `Cargo.toml` setup (edition 2024, deps: clap, serde, serde_json, walkdir, chrono, uuid)
- [ ] `SessionParser` trait: `fn parse(path: &Path) -> Result<Vec<Session>>`
- [ ] Unified `Session` type: messages, metadata, environment fingerprint, session type
- [ ] Unified `Message` type: role, content (text + thinking + tool_use + tool_result), timestamp, classification
- [ ] Claude Code parser (most complete schema — research documented all fields)
- [ ] Codex parser (session JSONL format — different envelope, message nesting)
- [ ] OpenClaw parser (similar to Codex but with multi-agent metadata)
- [ ] Gemini parser (directory-based, not JSONL — different approach needed)
- [ ] Cursor parser (stub — schema not yet documented)
- [ ] OpenCode parser (stub — schema not yet documented)
- [ ] Auto-detection: sniff first line of file to determine format
- [ ] Corpus discovery: scan default paths for each tool (`~/.claude/projects/`, `~/.codex/sessions/`, `~/.gemini/history/`, `~/openclaw-sessions/`)
- [ ] Session type classifier: interactive vs subagent using structural signals (tool_result presence, parentUuid chains, subagent path patterns)
- [ ] Message classifier: port the validated Python classifier (98% accuracy) to Rust. Structural-first (tool_result blocks), length-gated lexical, positional
- [ ] Environment fingerprinter: extract version, model, permissionMode, plugin/MCP references from session metadata
- [ ] Test fixtures: sample JSONL files for each format with known expected parses

**Verification:** `middens parse <file>` correctly parses session files from all supported formats and outputs classified messages as JSON.

#### Phase 2: Rust-Native Techniques

The 5-6 techniques that can be implemented in pure Rust without Python.

**Tasks:**
- [ ] `Technique` trait: `fn name() -> &str`, `fn run(sessions: &[Session]) -> TechniqueResult`, `fn requires_python() -> bool`
- [ ] `TechniqueResult` type: findings (key-value), data tables, figure specs, metadata
- [ ] Markov chain tool transitions: transition matrix, self-loop rates, entry/exit tools
- [ ] Entropy rate: sliding-window conditional entropy H(X|context), anomaly detection (mean ± 2σ)
- [ ] Shannon/Simpson diversity: per-session indices, species-area curve fitting, monoculture detection
- [ ] Burstiness coefficients: Barabási B and memory M per event type
- [ ] Correction rate metrics: per-session and per-project correction/approval ratios, maturity curve
- [ ] Technique registry: list available techniques, filter by `--techniques` flag

**Verification:** `middens analyze <path> --techniques markov,entropy,diversity` produces correct results matching the Third Thoughts research outputs on the same data.

#### Phase 3: Output Engine

Produce all output formats.

**Tasks:**
- [ ] YAML-frontmatter markdown report per technique (technique name, corpus size, timestamp, parameters, findings, methodology description)
- [ ] JSON data file per technique (all raw numbers, tables, matrices)
- [ ] Parquet files for tabular data (use `arrow2` or `polars` crate)
- [ ] Vega-Lite JSON specs for each chart type:
  - Line charts: survival curves, entropy trajectories
  - Bar charts: tool frequency, correction rates by project
  - Heatmaps: transition matrices, excitation matrices
  - Scatter plots: diversity vs. session length, foraging efficiency
- [ ] ASCII sparklines/mini-charts embedded in markdown reports (for terminal viewing)
- [ ] Results directory structure: `results/{timestamp}/` with per-technique subdirectories

**Verification:** Output files are valid (markdown parses, JSON validates, Parquet reads with DuckDB/polars, Vega-Lite renders in VS Code).

#### Phase 4: Python Bridge

The `uv`-managed Python subprocess for complex techniques.

**Tasks:**
- [ ] `uv` detection: check if `uv` is installed, offer to install if not
- [ ] Venv management: create/activate a managed venv at `~/.config/middens/python/` on first run
- [ ] `requirements.txt` with pinned versions: hmmlearn, statsmodels, lifelines, pm4py, prefixspan, scipy, numpy, pandas
- [ ] `PythonTechnique` wrapper: serializes session data to temp JSON/Parquet, calls Python script, parses JSON results
- [ ] Port/adapt all 13 complex technique scripts from `third-thoughts/scripts/` into `middens/python/techniques/`
- [ ] Standardize Python script interface: read input path from argv, write JSON results to stdout or output path
- [ ] Error handling: capture stderr, report Python failures clearly, fall back gracefully
- [ ] `--no-python` flag: skip all Python techniques, run only Rust-native ones

**Verification:** `middens analyze <path> --techniques hsmm,survival` correctly invokes Python and produces results matching the Third Thoughts outputs.

#### Phase 5: CLI Polish + Report Generator

The user-facing CLI and cross-technique synthesis.

**Tasks:**
- [ ] `middens analyze <path>` — full pipeline with progress output
- [ ] `middens analyze` (no path) — auto-discover and scan all default locations
- [ ] `middens analyze --split` — automatic interactive/subagent stratification (run techniques separately on each population)
- [ ] `middens analyze --techniques X,Y,Z` — run subset
- [ ] `middens analyze --all` — run full 23+ battery
- [ ] `middens list-techniques` — show available techniques with descriptions, Python requirement, estimated runtime
- [ ] `middens report <results-dir>` — generate consolidated cross-technique synthesis report
- [ ] `middens freeze <path>` — create corpus manifest with checksums
- [ ] `middens parse <file>` — debug: parse and dump a single session file
- [ ] `middens fingerprint <path>` — show environment evolution over time
- [ ] Progress reporting: per-technique progress, ETA, parallel technique execution
- [ ] Config file support: `~/.config/middens/config.toml` for default paths, technique selection, Python location
- [ ] Error reporting: clear messages when parsers fail, Python is missing, corpus is empty

**Verification:** End-to-end: `middens analyze ~/.claude/projects/` produces a complete results directory with reports, data, and figures for the essential 10 techniques within 30 minutes.

## Essential 10 Techniques (Default Battery)

Based on the Third Thoughts research — highest value, reasonable runtime:

| # | Technique | Implementation | Why essential |
|---|-----------|---------------|---------------|
| 1 | Thinking block divergence | Rust | The 85.5% risk suppression finding. Unique to this tool |
| 2 | Tool sequence mining (Markov) | Rust | Core behavioral fingerprint. Fast |
| 3 | Entropy rate + anomaly detection | Rust | Predictability measure. Rigid = failure signal |
| 4 | Ecology diversity (Shannon/Simpson) | Rust | Tool diversity as health metric |
| 5 | Burstiness coefficients | Rust | Correction self-excitation signal |
| 6 | Survival analysis (Kaplan-Meier + Cox) | Python | Time-to-correction curves. Key protective factors |
| 7 | HSMM behavioral states | Python | Pre-failure state detection (24.6x lift) |
| 8 | Lag sequential analysis | Python | Behavioral perseveration detection |
| 9 | Change-point detection (PELT) | Python | Session phase transitions |
| 10 | Information foraging | Python | Exploration efficiency. MVT testing |

Extended battery (via `--all`): Granger causality, T-pattern detection, PrefixSpan, process mining, ENA, SPC control charts, NCD clustering, Smith-Waterman alignment, convention epidemiology, cross-project graph, corpus analytics/NMF, user signal analysis, correction rate trends.

## Session Log Format Support

Based on research of actual files on this system:

| Tool | Format | Location | Status |
|------|--------|----------|--------|
| Claude Code | JSONL (rich — thinking, tools, metadata) | `~/.claude/projects/{hash}/{uuid}.jsonl` | Full schema documented |
| Codex CLI | JSONL (rich — messages, turn_context, model changes) | `~/.codex/sessions/{date}/{uuid}.jsonl` | Full schema documented |
| OpenClaw | JSONL (similar to Codex + multi-agent metadata) | `~/openclaw-sessions/{agent}.jsonl` | Full schema documented |
| Gemini CLI | Directory-based (not JSONL) | `~/.gemini/history/{project}/` | Needs different parser approach |
| Cursor | Unknown | `~/.cursor/` (not present on system) | Stub parser, schema TBD |
| OpenCode | Unknown | `~/.opencode/` (not present on system) | Stub parser, schema TBD |

## Dependencies (Cargo.toml)

```toml
[package]
name = "middens"
version = "0.1.0"
edition = "2024"

[dependencies]
clap = { version = "4", features = ["derive"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
walkdir = "2"
chrono = { version = "0.4", features = ["serde"] }
uuid = { version = "1", features = ["serde"] }
regex = "1"
sha2 = "0.10"           # for corpus manifest checksums
toml = "0.8"             # config file
polars = { version = "0.46", features = ["parquet", "json"] }  # Parquet output
```

## Acceptance Criteria

- [ ] R1: `middens` binary builds with `cargo build --release` from `third-thoughts/middens/`
- [ ] R2: Parser trait implemented; Claude Code, Codex, OpenClaw parsers pass tests against fixture files
- [ ] R3: `middens analyze ~/.claude/projects/` discovers and indexes all session files
- [ ] R4: Interactive/subagent classification matches the validated classifier (98% accuracy)
- [ ] R5: Essential 10 techniques run by default; `--all` adds the rest
- [ ] R6: `uv` auto-setup works on clean macOS and Linux systems
- [ ] R7: 5 techniques run in pure Rust with zero Python dependency
- [ ] R9: Each technique produces markdown + JSON + Parquet + Vega-Lite output
- [ ] R10: `middens report` generates a synthesis report from technique outputs
- [ ] R11: Correction classifier matches Python version's accuracy on the labeled dataset
- [ ] R12: `middens freeze` creates a reproducible manifest
- [ ] R14: `middens list-techniques` and `--techniques` flag work correctly
- [ ] R15: Environment fingerprint extracted from sessions and included in output
- [ ] R17: `--split` produces stratified results for interactive vs subagent

## Dependencies & Risks

- **Polars/Arrow crate size**: Polars is large. May need feature-gating or a lighter Parquet writer
- **Gemini parser**: Directory-based format is architecturally different from JSONL. May need a separate discovery path
- **Python script portability**: The 13 Python techniques were written for the Third Thoughts corpus. They need standardized I/O interfaces to work as subprocess scripts
- **Cursor/OpenCode schemas**: Unknown until someone with these tools provides sample logs. Ship as stubs
- **`uv` reliability**: Tested primarily on macOS. Linux support needs verification
- **Vega-Lite spec complexity**: Each chart type needs a hand-crafted spec. Start with the most common (line, bar, heatmap) and add others incrementally

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-20-middens-cli-requirements.md](docs/brainstorms/2026-03-20-middens-cli-requirements.md) — Key decisions: binary named `middens`, Rust + Python/uv, pluggable parsers for 6 tools, essential 10 techniques by default, Vega-Lite + Parquet + frontmatter markdown output, lives in `third-thoughts/middens/`

### Internal References

- Existing Rust pattern: `foundry-2/Cargo.toml` (edition 2024, BTreeMap convention)
- Monorepo conventions: `CLAUDE.md` (monorepo root)
- Analysis scripts to port: `third-thoughts/scripts/*.py` (26 scripts)
- Methods catalog: `third-thoughts/docs/methods-catalog.md`
- Correction classifier: `third-thoughts/scripts/correction_classifier.py`
- Labeled dataset: `third-thoughts/data/labeled-messages.json`
- CLI roadmap (v1-v4): `third-thoughts/todos/cli-tool-roadmap.md`

### External References

- clap v4: https://docs.rs/clap/latest/clap/
- polars: https://docs.rs/polars/latest/polars/
- Vega-Lite spec: https://vega.github.io/vega-lite/
- uv: https://docs.astral.sh/uv/
