# Third Thoughts CLI — Roadmap

## v1: Headless Analysis Engine

The core. Pull, build, run, get files.

- [ ] Multi-format JSONL parser library (Claude Code, Codex CLI, Gemini CLI, Cursor, OpenClaw)
- [ ] Session type classifier (interactive vs subagent) — structural, not regex
- [ ] Corpus discovery and indexing (find all session files on a machine)
- [ ] Port simple techniques to Rust: Markov chains, entropy rate, Shannon/Simpson diversity, burstiness coefficients, correction classification
- [ ] Python bridge for complex techniques: HSMM, Granger causality, survival analysis, process mining, Smith-Waterman, T-pattern detection, PrefixSpan, ENA, SPC, NCD clustering, epidemiology, lag sequential, information foraging
- [ ] `third-thoughts analyze <path>` — runs full battery, outputs markdown + JSON to results/
- [ ] `third-thoughts analyze --techniques survival,hsmm,entropy` — run subset
- [ ] `third-thoughts analyze --split` — automatic interactive/subagent stratification
- [ ] `third-thoughts report` — generate consolidated findings report from results
- [ ] Cross-platform: macOS, Linux. Windows stretch goal
- [ ] Validated correction classifier (the one being built now) bundled as default
- [ ] Frozen corpus manifest support for reproducibility

## v2: Ratatui TUI ("The Lab")

The research ops dashboard. Blade Runner meets htop.

- [ ] `third-thoughts analyze --interactive` launches TUI, `--exec` for headless (default)
- [ ] Multi-pane layout: technique grid + detail pane + findings feed + status bar
- [ ] Grid of squares: one per technique, fills up as each completes (dark → amber → green/red)
- [ ] Oscilloscope traces: one per running technique, amplitude = key metric (entropy, correction rate, diversity), frequency = event processing rate
- [ ] Viterbi path visualization: HSMM states flickering through S0-S6 as sessions are processed, color-coded by state
- [ ] Scrolling findings feed: key results appear as techniques complete, severity-colored
- [ ] Progress bars per technique with ETA
- [ ] Final convergent summary view: cross-technique agreement matrix
- [ ] Session browser: drill into individual sessions, see their state trajectories
- [ ] Keystroke navigation: tab between panes, enter to drill down, q to quit
- [ ] Export current view as screenshot (ANSI art or PNG)

## v3: Risk Surfacer

Real-time thinking block risk surfacing. See exploratory plan in docs/plans/.

- [ ] `third-thoughts watch` — tail session JSONL, surface suppressed risks in real time
- [ ] Severity classification: info / warning / critical
- [ ] Claude Code hook integration (if hook API supports thinking block access)
- [ ] MCP server mode: agent self-audit tool
- [ ] Hybrid mode: passive monitor + active escalation on high-severity

## v4: Federated Learning Daemon ("The Network")

Patterns travel, data stays home.

- [ ] `third-thoughts daemon` — background process, watches for new sessions
- [ ] Local analysis loop: runs techniques as corpus grows, stores findings locally
- [ ] Anonymized pattern extraction: findings stripped of content, only aggregate statistics
- [ ] Serverless backend: receives patterns from nodes, maintains meta-analysis registry
- [ ] Pattern registry: which patterns confirmed across how many operators/models/tools
- [ ] Technique distribution: backend pushes new experiments to nodes ("run this HSMM variant and report back")
- [ ] Node onboarding: new node gets current pattern catalog + technique battery
- [ ] Privacy guarantees: no session content leaves the machine, only aggregate stats + pattern metadata
- [ ] Multi-model meta-analysis: patterns tagged by model family, enabling cross-model comparison
- [ ] Dashboard: web UI showing the federated findings landscape

## Architecture Notes

- Rust for: JSONL parsing, corpus management, orchestration, simple techniques, TUI, daemon
- Python for: HSMM (hmmlearn), Granger (statsmodels), survival (lifelines), process mining (pm4py), PrefixSpan, Smith-Waterman, ENA, SPC, NCD, epidemiology, lag sequential, foraging
- Python env: `uv` for zero-config setup on first run
- Data flow: Rust → JSON/CSV → Python subprocess → JSON/CSV → Rust
- Config: TOML at `~/.config/third-thoughts/config.toml`
