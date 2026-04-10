# Worked example: the analyze → interpret → export triad

This walks through the full middens pipeline on a real corpus of Claude Code session logs.

## Prerequisites

- `middens` built and on `PATH` (or run `./target/release/middens` from the build dir)
- At least one LLM runner installed for `interpret` (optional — you can skip it with `export --no-interpretation`)

## Step 1: Analyze

```bash
middens analyze ~/.claude/projects/
```

What happens:
- Discovers `.jsonl` session files recursively under the given path
- Parses each file (Claude Code, Codex, and OpenClaw formats supported)
- Classifies messages and sessions
- Runs the technique battery (6 Rust-native + up to 17 Python via embedded `uv` bridge)
- Writes canonical storage to the XDG data dir

Output (example):

```
Analysis complete:
  sessions discovered: 2594
  sessions parsed: 2594
  parse errors: 0
  techniques run: 23
  technique errors: 0
  results written to: middens-results
```

The run is also stored under `~/.local/share/com.lightless-labs.third-thoughts/analysis/run-<uuid>/` with:
- `manifest.json` — run metadata, technique entries, corpus fingerprint
- `data/*.parquet` — one Parquet file per technique
- `sessions.parquet` — canonical sessions table
- `default-view.md` — quick human-readable summary

## Step 2: Interpret

```bash
middens interpret
```

What happens:
- Finds the latest analysis run under the XDG dir (sorted by UUIDv7 = chronological)
- Builds a prompt from the manifest + technique summaries + headline table excerpts
- Sends it to the first available LLM runner (`claude-code` → `codex` → `gemini` → `opencode`)
- The LLM produces per-technique conclusions marked with `<!-- technique: <slug> -->` markers
- Writes the interpretation to `~/.local/share/com.lightless-labs.third-thoughts/interpretation/<run-slug>/<uuid>-<runner>/`

To use a specific runner and model:

```bash
middens interpret --model codex/gpt-5.4-codex
middens interpret --model opencode/kimi-for-coding/k2p5
middens interpret --model claude-code/claude-opus-4-6
```

To preview the prompt without calling an LLM:

```bash
middens interpret --dry-run
```

## Step 3: Export

```bash
middens export
```

What happens:
- Finds the latest analysis run and the latest matching interpretation
- Renders a Jupyter notebook (`.ipynb`, nbformat v4) with:
  - Run metadata and corpus fingerprint
  - Per-technique sections with markdown summaries, findings tables, and pre-executed code cells loading the Parquet data
  - Cross-technique conclusions from the interpretation (if present)
- Writes `report.ipynb` in the current working directory

To export without an interpretation:

```bash
middens export --no-interpretation
```

To specify a custom output path:

```bash
middens export -o ~/Desktop/my-report.ipynb
```

## Step 4: Open the notebook

```bash
jupyter notebook report.ipynb
```

The notebook is self-contained — all technique data is embedded as pre-executed cell outputs. The Parquet paths in the code cells point back to the XDG storage dir, so re-running cells works if the run hasn't been deleted.

## Stratified analysis

For mixed corpora containing both interactive and subagent sessions:

```bash
# Step 1: analyze with --split
middens analyze ~/.claude/projects/ --split

# Step 2 + 3: operate per-stratum (v1 doesn't support cross-stratum)
middens interpret --analysis-dir ~/.local/share/com.lightless-labs.third-thoughts/analysis/run-<uuid>/interactive
middens export --analysis-dir ~/.local/share/com.lightless-labs.third-thoughts/analysis/run-<uuid>/interactive -o interactive-report.ipynb

middens interpret --analysis-dir ~/.local/share/com.lightless-labs.third-thoughts/analysis/run-<uuid>/subagent
middens export --analysis-dir ~/.local/share/com.lightless-labs.third-thoughts/analysis/run-<uuid>/subagent -o subagent-report.ipynb
```

## Storage layout reference

```
~/.local/share/com.lightless-labs.third-thoughts/
  analysis/
    run-<uuidv7>/
      manifest.json
      data/
        entropy.parquet
        markov.parquet
        ...
      sessions.parquet
      default-view.md
  interpretation/
    run-<uuidv7>/
      <uuidv7>-<runner>/
        manifest.json
        conclusions.md
        entropy-conclusions.md
        markov-conclusions.md
        ...
        prompt.md
  interpretation-failures/       # failed interpretations land here
  interpretation-dryruns/        # --dry-run output lands here
```
