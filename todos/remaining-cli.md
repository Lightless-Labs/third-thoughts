# Remaining CLI Work

## Commands
- [ ] **`middens fingerprint <path>`** — Implement environment fingerprint extraction. Stubs exist at `src/fingerprint/{extract,evolution}.rs`. Extract: tool version, model ID, permission mode, MCP servers, plugins, hooks, CLAUDE.md hash from session metadata. Track changes over time across sessions
- [ ] **`middens report <results-dir>`** — Cross-technique synthesis report generator. Read technique results from a previous `analyze` run, identify convergent findings, produce a consolidated markdown report

## Output Formats
- [ ] **Parquet export** — Add `polars` or `arrow2` dep. Write `.parquet` per technique alongside `.md` and `.json`. Machine-readable tabular data for Python/DuckDB downstream analysis
- [ ] **Vega-Lite figure specs** — Generate `.vl.json` per technique with chart definitions (line charts for entropy, heatmaps for transition matrices, bar charts for tool frequencies). Renderable in VS Code, notebooks, browsers

## Pipeline Improvements
- [ ] **Progress reporting** — Show per-technique progress during `analyze` runs (technique name, elapsed time, ETA)
- [ ] **Parallel technique execution** — Run techniques concurrently via `std::thread::scope`. Currently sequential
- [ ] **Config file** — `~/.config/middens/config.toml` for default corpus path, technique selection, Python location, output format preferences

## Parsers
See `todos/additional-parsers.md`: OpenCode, Cursor, Gemini CLI full, Aider
