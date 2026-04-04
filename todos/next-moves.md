# Next Moves — All Outstanding Work

## Middens CLI

### Done (for reference)
- [x] Phase 1: Parsers (Claude Code, Codex, OpenClaw), classifiers, corpus discovery
- [x] Phase 2: 5 Rust-native techniques (markov, entropy, diversity, burstiness, correction-rate)
- [x] Phase 3 core: Output engine (markdown, JSON, ASCII renderers)
- [x] Phase 5 partial: `analyze`, `parse`, `freeze`, `list-techniques` wired
- [x] `--split` automatic interactive/subagent stratification
- [x] Thinking block divergence technique (85.5% risk suppression)
- [x] Cucumber/Gherkin BDD test suite (199 scenarios)
- [x] Public repo at github.com/Lightless-Labs/third-thoughts
- [x] `rust-version = "1.88"` in Cargo.toml

### Extended Output Formats
- [ ] **Parquet export.** Add `polars` or `arrow2` crate. Write `.parquet` per technique alongside `.md` and `.json`. Useful for downstream analysis in Python/DuckDB. Requires new dep + output module.
- [ ] **Vega-Lite figure specs.** Generate `.vl.json` per technique with chart definitions (line charts for entropy trajectories, heatmaps for transition matrices, bar charts for tool frequencies). Renderable in VS Code, notebooks, browsers.

### Phase 4: Python Bridge
- [ ] **`uv` detection and venv management.** Auto-detect or install `uv`, create managed venv at `~/.config/middens/python/`
- [ ] **`PythonTechnique` wrapper.** Serialize session data to temp JSON, call Python script, parse JSON results back
- [ ] **`requirements.txt` with pinned versions.** hmmlearn, statsmodels, lifelines, pm4py, prefixspan, scipy, numpy, pandas
- [ ] **Port 13 complex technique scripts.** From `scripts/` into `middens/python/techniques/` with standardized I/O interface
- [ ] **`--no-python` flag.** Already in CLI args, needs to actually filter (no Python techniques exist yet)

### Remaining CLI Work
- [ ] **`middens fingerprint`** — implement environment fingerprint extraction (stubs exist at `src/fingerprint/`)
- [ ] **`middens report`** — cross-technique synthesis generator (convergent findings across techniques)
- [ ] **Progress reporting.** Show per-technique progress during `analyze` runs
- [ ] **Parallel technique execution.** Run techniques concurrently (currently sequential)
- [ ] **Config file.** `~/.config/middens/config.toml` for default paths, technique selection, Python location

### Review Fixes
See `todos/middens-review-triage.md` for full list:
- P1: Burstiness cross-session contamination, population vs sample variance, entropy sessions_skipped, short session positional analysis
- P2: ASCII table byte/char width, test epsilon hack, double format_value, bar chart negative max, YAML parameter key quoting

### Additional Parsers
See `todos/additional-parsers.md`: OpenCode, Cursor, Gemini CLI full, Aider

## Research Reruns

- [ ] **Rerun Granger causality on interactive-only with corrected classifier.** Classifier is built (`scripts/correction_classifier.py`). Modify `scripts/granger_causality.py` to use it, run on `corpus-split/interactive/`
- [ ] **Rerun survival analysis on interactive-only with corrected classifier.** Determines if thinking-block protective effect is real or confounded
- [ ] **Rerun process mining on interactive-only with corrected classifier.** Validate "7x more thinking in low-correction sessions"

## Content

- [ ] **"Selling the Sawdust" v3 article.** Incorporate population split lesson, new techniques, contamination narrative, corrected findings
- [ ] **Methods catalog update.** Add Doors and Corners protocol. Update technique descriptions per peer review feedback

## Risk Surfacing Tool

- [ ] **Proof of concept.** CLI that tails session JSONL, extracts suppressed risks from thinking blocks, prints to side terminal. See `docs/plans/2026-03-20-002-feat-risk-surfacing-tool-exploratory-plan.md`
- [ ] **Severity classifier.** Keyword + context based severity model for surfaced risks

## Middens v2-v4 (Future)

See `todos/cli-tool-roadmap.md`:
- [ ] v2: Ratatui TUI ("The Lab")
- [ ] v3: Risk Surfacer — real-time thinking block monitoring
- [ ] v4: Federated Learning Daemon ("The Network")

## Infrastructure

- [ ] **Corpus manifest checksums.** Current `corpus-frozen/MANIFEST.txt` is file paths only. Add SHA-256 for reproducibility (use `middens freeze`)
- [ ] **Bazel migration.** Lightless Labs convention says Bazel. Evaluate when monorepo matures
