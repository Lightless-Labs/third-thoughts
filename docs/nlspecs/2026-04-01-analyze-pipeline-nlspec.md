---
date: 2026-04-01
topic: middens-analyze-pipeline
source_spec: docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md
status: draft
---

# Middens Analyze Pipeline

## 1. Why

### 1.1 Problem Statement

The middens CLI has all the pieces — parsers, classifiers, 5 techniques, and an output engine — but no way to run them together. The `analyze` command prints "[not yet implemented]". A user who wants to analyze their agent session logs has to call `parse`, then manually construct `Session` objects, run each technique individually, and render output by hand. The pipeline wires these pieces into a single `middens analyze <path>` invocation.

### 1.2 Design Principles

- **Wire, don't rewrite.** Every component already exists and is tested. The pipeline calls existing functions in sequence. No new algorithms, no new data types beyond a lightweight pipeline config.
- **Fail gracefully, report clearly.** Individual file parse failures or technique errors should not abort the entire run. Report failures to stderr and continue with what succeeded.
- **Output is files on disk.** Each technique produces a markdown report and a JSON data file in the output directory. The user gets a directory of results they can browse.

### 1.3 Layering and Scope

The pipeline covers:
- The `analyze` subcommand in `main.rs`
- A pipeline orchestration module at `src/pipeline.rs`
- Results directory management
- Progress reporting to stderr

Out of scope: `--split` stratification (future), `middens report` cross-technique synthesis (future), Python bridge techniques (Phase 4), config file support.

## 2. What

### 2.1 Data Model

```text
RECORD PipelineConfig:
  corpus_path: Option<Path>       -- None = auto-discover
  output_dir: Path                -- default "middens-results"
  technique_filter: TechniqueFilter
  no_python: bool

ENUM TechniqueFilter:
  Essential                       -- default: is_essential() == true
  All                             -- all registered techniques
  Named(Vec<String>)              -- specific technique names

RECORD PipelineResult:
  sessions_discovered: usize
  sessions_parsed: usize
  parse_errors: usize
  techniques_run: usize
  technique_errors: usize
  output_dir: Path
```

### 2.2 Architecture

```text
main.rs (CLI args)
  → pipeline::run(config) -> Result<PipelineResult>
      → corpus::discovery::discover_sessions(path)
      → for each file: parser::auto_detect::parse_auto(file)
          (collect sessions, log parse errors to stderr)
      → techniques::all_techniques() filtered by TechniqueFilter
      → for each technique: technique.run(&sessions)
          (collect results, log technique errors to stderr)
      → for each result: write markdown + JSON to output_dir
      → return PipelineResult summary
  → print summary to stderr
```

### 2.3 Vocabulary

- **Pipeline**: The sequence discover → parse → filter techniques → run → write output
- **Corpus path**: Directory containing session log files (or None for auto-discovery)
- **Output directory**: Where results are written (default `middens-results/`)
- **Technique filter**: Which techniques to run (essential, all, or named subset)

## 3. How

### 3.1 Pipeline Module

```text
FUNCTION run(config: PipelineConfig) -> Result<PipelineResult>:
  -- Step 1: Discover session files
  files = discover_sessions(config.corpus_path)
  eprintln("Discovered {} session files", files.len())
  IF files is empty:
    eprintln("No session files found.")
    RETURN Ok(PipelineResult with all zeros)

  -- Step 2: Parse all files, collecting sessions and logging errors
  sessions = []
  parse_errors = 0
  FOR file IN files:
    MATCH parse_auto(file):
      Ok(parsed) => sessions.extend(parsed)
      Err(e) => {
        eprintln("  ✗ Failed to parse {}: {}", file, e)
        parse_errors += 1
      }
  eprintln("Parsed {} sessions from {} files ({} errors)",
           sessions.len(), files.len(), parse_errors)
  IF sessions is empty:
    eprintln("No sessions parsed successfully.")
    RETURN Ok(PipelineResult with parse info, zeros for techniques)

  -- Step 3: Select techniques
  all_techs = all_techniques()
  selected = MATCH config.technique_filter:
    Essential => all_techs.filter(|t| t.is_essential())
    All => all_techs
    Named(names) => all_techs.filter(|t| names.contains(t.name()))
  IF config.no_python:
    selected = selected.filter(|t| !t.requires_python())
  eprintln("Running {} techniques: {}", selected.len(),
           selected.map(|t| t.name()).join(", "))

  -- Step 4: Create output directory
  create_dir_all(config.output_dir)

  -- Step 5: Run techniques and write output
  techniques_run = 0
  technique_errors = 0
  meta = OutputMetadata {
    technique_name: "",  -- filled per technique
    corpus_size: sessions.len(),
    generated_at: now_iso8601(),
    middens_version: env!("CARGO_PKG_VERSION"),
    parameters: {}
  }
  FOR technique IN selected:
    eprintln("  ▸ Running {}...", technique.name())
    MATCH technique.run(&sessions):
      Ok(result) => {
        meta.technique_name = technique.name()
        -- Write markdown report
        md = render_markdown(&result, &meta)
        write(output_dir / "{}.md".format(technique.name()), md)
        -- Write JSON data
        json = render_json(&result, &meta)
        write(output_dir / "{}.json".format(technique.name()),
              to_string_pretty(json))
        eprintln("  ✓ {} complete", technique.name())
        techniques_run += 1
      }
      Err(e) => {
        eprintln("  ✗ {} failed: {}", technique.name(), e)
        technique_errors += 1
      }

  -- Step 6: Print summary
  eprintln("")
  eprintln("Results written to {}", output_dir)
  eprintln("  Sessions: {} parsed ({} errors)",
           sessions.len(), parse_errors)
  eprintln("  Techniques: {} complete ({} errors)",
           techniques_run, technique_errors)

  RETURN Ok(PipelineResult { ... })
```

### 3.2 CLI Wiring

```text
FUNCTION main() — Commands::Analyze branch:
  config = PipelineConfig {
    corpus_path: path,
    output_dir: output,
    technique_filter: IF all THEN All
                      ELSE IF techniques.is_some() THEN Named(techniques)
                      ELSE Essential,
    no_python: no_python
  }
  result = pipeline::run(config)?
  -- Exit with non-zero if no sessions were parsed
  IF result.sessions_parsed == 0:
    exit(1)
  Ok(())
```

## 4. Out of Scope

- `--split` automatic stratification (run separately on interactive/subagent)
- `middens report` cross-technique synthesis
- Python bridge / `--no-python` actually filtering (no Python techniques exist yet)
- Config file (`~/.config/middens/config.toml`)
- Progress bars or ETA estimation
- Parallel technique execution (run sequentially for v1 simplicity)

## 5. Design Decision Rationale

**Why a separate `pipeline.rs` module instead of inline in main?** Testability — the pipeline function takes a config and returns a result, which can be tested without invoking clap. `main.rs` stays thin.

**Why sequential technique execution?** Simpler, easier to debug, and the 5 Rust-native techniques are fast enough. Parallel execution is a future optimization.

**Why exit(1) on zero sessions?** A pipeline that parses nothing is a user error (wrong path, empty corpus). Non-zero exit lets shell scripts detect failure.

**Why both markdown and JSON per technique?** Markdown is human-readable, JSON is machine-consumable. Both are cheap to produce since the output engine already exists.

## 6. Definition of Done

### 6.1 Pipeline Module (mirrors 3.1)
- [ ] `pipeline::run(config)` discovers session files from the corpus path
- [ ] Auto-discovers default locations when corpus_path is None
- [ ] Parses all discovered files, collecting sessions
- [ ] Parse errors are reported to stderr but don't abort the pipeline
- [ ] Selects techniques based on TechniqueFilter (Essential, All, Named)
- [ ] `no_python` flag filters out Python-requiring techniques
- [ ] Named filter with unknown technique name is reported but doesn't abort
- [ ] Runs each selected technique on the parsed sessions
- [ ] Technique errors are reported to stderr but don't abort the pipeline
- [ ] Creates the output directory if it doesn't exist
- [ ] Writes a `.md` file per technique using render_markdown
- [ ] Writes a `.json` file per technique using render_json
- [ ] Returns PipelineResult with correct counts (discovered, parsed, parse_errors, techniques_run, technique_errors)
- [ ] Empty corpus (no files found) returns Ok with zero counts, does not error
- [ ] Zero successfully parsed sessions returns Ok with zero technique counts

### 6.2 CLI Wiring (mirrors 3.2)
- [ ] `middens analyze <path>` runs the pipeline on the given path
- [ ] `middens analyze` with no path auto-discovers
- [ ] `--techniques markov,entropy` runs only named techniques
- [ ] `--all` runs all techniques
- [ ] Default (no flags) runs essential techniques only
- [ ] `--no-python` excludes Python techniques
- [ ] `--output <dir>` sets the output directory (default: middens-results)
- [ ] Exit code is 0 when sessions were parsed, 1 when none were

### 6.3 Output Files
- [ ] Output directory contains `{technique_name}.md` for each run technique
- [ ] Output directory contains `{technique_name}.json` for each run technique
- [ ] Markdown files have valid YAML frontmatter with corpus_size matching session count
- [ ] JSON files are valid JSON parseable by any JSON parser

### 6.4 Integration
- [ ] End-to-end: `middens analyze tests/fixtures/ -o /tmp/test-results` produces 5 markdown + 5 JSON files (one per Rust technique)
- [ ] Smoke test: output directory exists and contains expected files after a run
