# Next Moves — All Outstanding Work

## Middens CLI

### Phase 2: Rust-Native Techniques
- [ ] Implement `Technique` trait with `TechniqueResult` output type
- [ ] Implement Markov chain tool transitions (transition matrix, self-loop rates)
- [ ] Implement entropy rate + anomaly detection (sliding-window conditional entropy)
- [ ] Implement Shannon/Simpson diversity indices + species-area curve fitting
- [ ] Implement burstiness coefficients (Barabási B and memory M)
- [ ] Implement correction rate metrics (per-session, per-project, maturity curve)
- [ ] Implement thinking block divergence (risk suppression, divergence rates)
- [ ] Technique registry with `--techniques` flag filtering

### Phase 3: Output Engine
- [ ] YAML-frontmatter markdown report per technique
- [ ] JSON data files
- [ ] Parquet export (polars or arrow2)
- [ ] Vega-Lite JSON specs for figures
- [ ] ASCII sparklines embedded in markdown reports
- [ ] Results directory structure

### Phase 4: Python Bridge
- [ ] `uv` detection, installation, venv management
- [ ] `requirements.txt` with pinned versions
- [ ] `PythonTechnique` wrapper (serialize data, call script, parse results)
- [ ] Port/adapt 13 complex technique scripts into `middens/python/techniques/`
- [ ] Standardize Python script I/O interface
- [ ] `--no-python` flag

### Phase 5: CLI Wiring + Report Generator
- [ ] Wire `middens analyze` to actual pipeline (discovery → parse → classify → techniques → output)
- [ ] Wire `middens parse` to parser + JSON output
- [ ] Wire `middens freeze` to manifest creation
- [ ] Wire `middens fingerprint` to environment fingerprinter
- [ ] Wire `middens list-techniques` to technique registry
- [ ] `middens report` cross-technique synthesis generator
- [ ] `middens analyze --split` automatic stratification
- [ ] Progress reporting and parallel technique execution
- [ ] Config file support (`~/.config/middens/config.toml`)

### Review Fixes (P2/P3)
See `todos/middens-review-triage.md` for full list.

### Additional Parsers
See `todos/additional-parsers.md` for full list (OpenCode, Cursor, Gemini CLI full, Aider, etc.)

## Research Reruns

- [ ] **Rerun Granger causality on interactive-only with corrected classifier.** The classifier is built (`scripts/correction_classifier.py`). Need to modify `scripts/granger_causality.py` to use it, then run on `corpus-split/interactive/`. This resolves whether thinking actually Granger-causes fewer corrections
- [ ] **Rerun survival analysis on interactive-only with corrected classifier.** Same: modify `scripts/survival_analysis.py` to use the structural classifier, rerun on interactive split. Determines if the thinking-block protective effect is real or confounded
- [ ] **Rerun process mining on interactive-only with corrected classifier.** The "7x more thinking in low-correction sessions" finding needs validation with proper correction detection

## Content

- [ ] **"Selling the Sawdust" v3 article.** Incorporate: population split lesson, new techniques (HSMM, foraging, Granger), the contamination narrative (research tool demonstrating the failure mode it studies, again), corrected findings
- [ ] **Methods catalog update.** Add the Doors and Corners protocol as a new method family. Update any technique descriptions based on peer review feedback

## Risk Surfacing Tool

- [ ] **Proof of concept.** Phase 1 from `docs/plans/2026-03-20-002-feat-risk-surfacing-tool-exploratory-plan.md`: CLI that tails session JSONL, extracts suppressed risks from thinking blocks, prints them to a side terminal
- [ ] **Severity classifier.** Keyword + context based severity model for surfaced risks

## Middens v2-v4 (Future)

See `todos/cli-tool-roadmap.md` for:
- [ ] v2: Ratatui TUI ("The Lab") — Blade Runner meets htop
- [ ] v3: Risk Surfacer — real-time thinking block monitoring
- [ ] v4: Federated Learning Daemon ("The Network") — patterns travel, data stays home

## Infrastructure

- [ ] **Freeze corpus snapshot.** Current manifest is file paths only (`corpus-frozen/MANIFEST.txt`). Add SHA-256 checksums for true reproducibility
- [ ] **Set up git remote.** Third-thoughts repo has no remote. Push to GitHub/Gitea when ready
- [ ] **Bazel migration.** Lightless Labs convention says Bazel, but nothing uses it yet. Evaluate when middens is more mature
