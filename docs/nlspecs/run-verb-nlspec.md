---
title: "middens run — end-to-end pipeline verb"
status: draft
created: 2026-04-14
---

# NLSpec: `middens run`

## Why

`analyze`, `interpret`, and `export` exist as independent verbs. There is no single command to chain them. Users and the landing page demo need a one-shot invocation: point at a corpus, get a notebook. Without it, distribution means teaching three commands instead of one.

## What (Definition of Done)

- `middens run <corpus>` chains the full pipeline: **analyze → interpret → export**
- `--model <runner/model-id>` selects the interpretation runner+model (e.g. `claude-code/claude-opus-4-6`, `codex/o4-mini`). If omitted, the interpret step is **skipped** and the notebook is exported from raw analysis only.
- `--format jupyter` (default, and currently only option) selects the export format.
- `-o / --output <path>` sets the notebook output path. Default: `report.ipynb` in the current working directory.
- `--techniques <list>`, `--all`, `--no-python`, `--timeout <s>`, `--force` pass through unchanged to the analyze step (same semantics as `middens analyze`).
- `--no-interpretation` forces the interpret step to be skipped even when `--model` is given. Useful for debugging the analysis + export path without invoking an LLM.
- `--dry-run` passes through to interpret: writes the prompt to disk without calling a runner. Export still runs (against whatever interpretation output exists, or without it if none exists).
- If interpret **fails** (runner binary not on PATH, non-zero exit, or any other error), the command **hard-fails** immediately with a clear error message. No silent fallback to analysis-only export.
- Progress is printed to **stderr** at each stage boundary:
  - `→ analyzing <corpus>...`
  - `→ interpreting with <runner>/<model>...` (only if interpret step runs)
  - `→ exporting to <output-path>...`
- Summary line at the end (to stderr): sessions discovered/parsed, techniques run, output path.
- Exit 0 on full success, non-zero on any stage failure.

## How (implementation)

All changes live in `middens/src/main.rs` unless the match arm exceeds ~60 lines, in which case extract to `middens/src/commands/run.rs` following the pattern of `commands/interpret.rs`.

### CLI shape

Add a `Run { ... }` variant to the `Commands` enum:

```rust
/// Run the full pipeline: analyze → interpret → export.
Run {
    /// Path to session logs directory.
    path: Option<PathBuf>,

    /// Runner and model in <runner>/<model-id> format (e.g. claude-code/claude-opus-4-6).
    /// If omitted, the interpret step is skipped.
    #[arg(long)]
    model: Option<String>,

    /// Output file for the exported notebook.
    #[arg(short, long)]
    output: Option<PathBuf>,

    /// Export format (v1: jupyter only).
    #[arg(long, default_value = "jupyter")]
    format: ExportFormatCli,

    /// Run all techniques (not just essential 10).
    #[arg(long)]
    all: bool,

    /// Run specific techniques (comma-separated).
    #[arg(long, value_delimiter = ',')]
    techniques: Option<Vec<String>>,

    /// Skip Python-dependent techniques.
    #[arg(long)]
    no_python: bool,

    /// Override the auto-computed Python technique timeout (seconds).
    #[arg(long)]
    timeout: Option<u64>,

    /// Bypass timeout floor/ceiling checks. Only meaningful with --timeout.
    #[arg(long)]
    force: bool,

    /// Skip the interpret step even when --model is given.
    #[arg(long)]
    no_interpretation: bool,

    /// Write interpret prompt to disk without calling a runner.
    #[arg(long)]
    dry_run: bool,
},
```

### Match arm logic (pseudocode)

```
1. Validate flags (same --force requires --timeout rule as analyze).

2. Emit "→ analyzing <path or 'auto'>..." to stderr.
   Call pipeline::run(PipelineConfig { corpus_path: path, output_dir: "middens-results", ... }).
   Capture result. If sessions_parsed == 0, bail with "analyze step: no sessions parsed".
   The key output: result.output_dir — this is the analysis_dir for subsequent steps.

3. Determine whether to interpret:
   let do_interpret = model.is_some() && !no_interpretation;

4. If do_interpret:
   Emit "→ interpreting with <model>..." to stderr.
   Call interpret::run_interpret(InterpretConfig {
       analysis_dir: Some(result.output_dir.clone()),
       model,
       output_dir: None,   // let interpret pick the XDG path
       dry_run,
   }).
   On error: bail!("interpret step failed: {err}").

5. Emit "→ exporting to <output-path>..." to stderr.
   Call export::run_export(ExportConfig {
       analysis_dir: Some(result.output_dir),
       interpretation_dir: None,   // let export discover from XDG
       no_interpretation: !do_interpret,
       format: ExportFormat::Jupyter,
       output,
       force: true,   // run owns its output path
   }).
   On error: bail!("export step failed: {err}").

6. Print summary to stderr.
```

### Key invariants

- **No changes to `pipeline`, `interpret`, or `export` internals.** `run` is purely an orchestrator that calls existing public APIs.
- `force: true` in ExportConfig is intentional — `run` controls the output path, so overwrite is safe.
- When `--dry-run` is set and interpret is active, export still runs (it will find no new interpretation output and fall through to analysis-only, which is acceptable for a dry run).

## Done (acceptance criteria)

1. `cargo build --release` succeeds with no new warnings.
2. `cargo test` passes (332/332 scenarios).
3. `middens run --help` lists all flags with accurate descriptions.
4. `middens run <path> --all --no-python` completes without error (analyze + export only, no LLM call).
5. `middens run <path> --model claude-code/claude-opus-4-6 -o /tmp/test.ipynb` runs all three stages and produces a `.ipynb` file.
6. `middens run <path> --model badrunner/x` hard-fails with a non-zero exit and a message containing "interpret step failed".
