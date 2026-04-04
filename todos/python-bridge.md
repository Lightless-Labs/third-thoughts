# Phase 4: Python Bridge

Unlock the remaining 13 complex analytical techniques via Python subprocess.

## Prerequisites
- Python 3.9+ on target system
- `uv` for zero-config venv management

## Tasks

### Infrastructure
- [ ] **`uv` detection and auto-install.** Check if `uv` is installed. If not, offer to install via `curl`. Create managed venv at `~/.config/middens/python/` on first run
- [ ] **`requirements.txt` with pinned versions.** hmmlearn, statsmodels, lifelines, pm4py, prefixspan, scipy, numpy, pandas
- [ ] **`PythonTechnique` wrapper.** Serialize session data to temp JSON, spawn Python subprocess, parse JSON results back into `TechniqueResult`. Handle timeouts, stderr capture, non-zero exit codes
- [ ] **Standardized Python script I/O interface.** Each script reads input JSON from argv path, writes output JSON to stdout or argv output path. Standard schema for input (sessions) and output (findings, tables, figures)
- [ ] **`--no-python` flag wiring.** Already in CLI args — wire to actually filter `requires_python()` techniques (currently no Python techniques exist)

### Technique Ports (from scripts/ into middens/python/techniques/)
- [ ] HSMM behavioral states (hmmlearn) — pre-failure state detection, 24.6x correction lift
- [ ] Granger causality (statsmodels) — thinking → correction causal analysis
- [ ] Survival analysis (lifelines) — Kaplan-Meier + Cox PH, time-to-correction curves
- [ ] Process mining (pm4py) — Inductive Miner, conformance checking
- [ ] Smith-Waterman alignment (scipy) — deliberation motif enrichment
- [ ] T-pattern detection — temporal pattern discovery
- [ ] PrefixSpan mining — sequential pattern mining
- [ ] Epistemic Network Analysis — planning centrality as trap indicator
- [ ] SPC control charts — statistical process control for session quality
- [ ] NCD compression clustering — structural session archetypes
- [ ] Convention epidemiology — SIR model for convention propagation
- [ ] Lag sequential analysis — behavioral perseveration detection
- [ ] Information foraging — MVT violation, patch exploration efficiency

## Architecture
```
Rust (pipeline.rs)
  → PythonTechnique::run(&sessions)
    → serialize sessions to /tmp/middens-input-{uuid}.json
    → uv run python/techniques/{name}.py /tmp/middens-input-{uuid}.json
    → parse stdout JSON as TechniqueResult
    → clean up temp files
```

## Notes
- Each Python script should be independently runnable: `uv run python/techniques/hsmm.py input.json`
- Error handling: Python failures → technique_errors counter, pipeline continues
- The existing scripts in `scripts/` are the reference implementations — port and standardize, don't rewrite
