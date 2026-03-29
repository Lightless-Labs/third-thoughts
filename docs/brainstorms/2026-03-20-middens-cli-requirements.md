---
date: 2026-03-20
topic: middens-cli
---

# Middens: AI Agent Session Log Analyzer

## Problem Frame

Developers using AI coding agents (Claude Code, Codex, Gemini, Cursor, OpenClaw, OpenCode) generate gigabytes of session transcripts that are never looked at twice. These "digital middens" contain rich behavioral data — hidden reasoning, failure patterns, interaction dynamics, tool usage ecology — that is invisible during interactive use. The Third Thoughts research project proved that 23 analytical techniques from 14 academic disciplines can extract actionable findings from this data (e.g., 85.5% risk suppression, pre-failure state detection at 24.6x correction lift, agents under-exploring patches).

No tool exists to run this analysis. The techniques currently live as ad-hoc Python scripts requiring manual path configuration, dependency management, and result interpretation. A developer who wants to understand their own agent usage patterns has no way to do it.

## Requirements

- R1. **CLI binary named `middens`**, written in Rust, living at `lightless-labs/third-thoughts/middens/` in the Lightless Labs monorepo (Bazel build system)
- R2. **Pluggable parser architecture** with a parser trait/interface. Ship with parsers for: Claude Code, Codex CLI, Gemini CLI, Cursor, OpenClaw, OpenCode. Adding a new format should be a single-file PR implementing the trait
- R3. **Corpus discovery**: `middens analyze <path>` scans a directory recursively for session files, auto-detects format per file, and indexes them. `middens analyze` with no path auto-discovers default session log locations for each supported tool
- R4. **Session type classification**: automatically distinguish interactive sessions (human-in-the-loop) from subagent/automated sessions using structural signals (not regex). Report results stratified by default
- R5. **Essential 10 techniques run by default**. Full battery of 23+ available via `--all` or `--techniques survival,hsmm,entropy`. The essential 10 are the highest-value, lowest-runtime techniques from the Third Thoughts research
- R6. **Python bridge via `uv`**: on first run, auto-detect or install `uv`, create a managed venv, install Python dependencies. Zero manual user action required beyond having Python on the system
- R7. **Simple techniques in pure Rust**: Markov chains, entropy rate, Shannon/Simpson diversity, burstiness coefficients, correction classification — these run without Python
- R8. **Complex techniques via Python subprocess**: HSMM, Granger causality, survival analysis, process mining, Smith-Waterman, T-pattern detection, PrefixSpan, ENA, SPC, NCD clustering, epidemiology, lag sequential, information foraging — Rust orchestrates, passes data as JSON/Parquet, Python computes, returns results
- R9. **Output format**: for each technique, produce:
  - Frontmatter markdown report (YAML frontmatter with metadata: technique name, corpus size, timestamp, parameters)
  - JSON data file with all raw numbers
  - Parquet file for tabular raw data (CSV fallback)
  - Vega-Lite JSON specs for figures (renderable in browsers, notebooks, VS Code). ASCII sparklines/mini-charts embedded in the markdown for terminal viewing
- R10. **Consolidated report**: `middens report <results-dir>` generates a cross-technique synthesis report (like the Third Thoughts full-corpus report), identifying convergent findings and cross-technique agreement
- R11. **Validated correction classifier** bundled as the default message classifier. Structural-first (tool_result detection), length-gated lexical, positional. The classifier built in the Third Thoughts research (98% accuracy, 100% subagent accuracy)
- R12. **Reproducibility**: frozen corpus manifest support. `middens freeze <path>` creates a manifest of file paths + checksums without copying data
- R13. **Cross-platform**: macOS and Linux. Windows as stretch goal
- R14. **Technique selection**: `middens analyze --techniques survival,hsmm` runs a subset. `middens list-techniques` shows available techniques with descriptions and whether they require Python

## Success Criteria

- A developer can clone the repo, build with Bazel, and run `middens analyze ~/.claude/projects/` to get a findings report within 30 minutes on a typical corpus
- The essential 10 techniques produce results consistent with the Third Thoughts research when run on the same data
- Interactive/subagent stratification is automatic — no user configuration needed
- Adding a new session log format requires implementing one trait and adding one test file
- Output is usable by academics (citable reports with methodology descriptions) and power users (queryable data files)

## Scope Boundaries

- v1 is headless CLI only. No TUI (that's v2)
- No real-time watching/monitoring (that's v3 risk surfacer)
- No network communication or telemetry (that's v4 federated daemon)
- No web UI
- No LLM-based analysis or extraction — middens uses only deterministic/statistical techniques
- Does not modify session logs — read-only access

## Key Decisions

- **Binary name**: `middens` — archaeological garbage heaps that reveal more than monuments. Pairs with The Trawl (nautical waste → value) from The Daily Claude
- **Primary audience**: Power users who generate GBs of agent transcripts, with academic appeal (reproducibility, methodology descriptions, citable output)
- **Relationship to The Trawl**: completely separate tools, different goals. No shared code
- **Python dependency**: managed via `uv` auto-setup on first run. Not embedded (PyO3) or eliminated (all-Rust)
- **Default technique set**: essential 10, not all 23. Full battery opt-in via `--all`
- **Figures**: Vega-Lite JSON specs + ASCII terminal fallbacks. No raster images generated
- **Raw data**: Parquet primary, CSV fallback
- **Reports**: YAML-frontmatter markdown
- **Repo location**: `lightless-labs/third-thoughts/middens/`, nested in the research project, Bazel build

## Dependencies / Assumptions

- Bazel is the build system (per Lightless Labs conventions)
- Python 3.9+ available on target systems (for `uv` to work)
- Session log formats for all 6 tools are stable enough to parse (format changes may break parsers)
- The 23 techniques from Third Thoughts are the starting analytical battery; more can be added later via the pluggable architecture

## Requirements (continued)

- R15. **Environment fingerprinting**: for each session, extract and record the active configuration — installed MCP servers, plugins/skills, hooks, CLAUDE.md content hash, permission mode, model ID, system prompt fragments. This is the "setup" that shaped the agent's behavior during that session
- R16. **Environment evolution tracking**: across sessions over time, detect when the environment changed (new plugin installed, CLAUDE.md updated, hook added) and correlate configuration changes with behavioral shifts (correction rate, tool diversity, entropy). The environment is a hidden covariate in every analysis
- R17. **Configuration-stratified analysis**: just as we stratify by interactive/subagent, optionally stratify by environment fingerprint. Sessions with Compound Engineering plugin vs without. Sessions with hooks vs without. Sessions before/after a CLAUDE.md update

## Outstanding Questions

### Deferred to Planning
- [Affects R15][Needs research] What environment signals are reliably present in each tool's session logs? Claude Code JSONL includes `version`, `permissionMode`, and sometimes system-reminder content with plugin/MCP info. Other tools may expose more or less. Need to audit each format
- [Affects R16][Technical] How to detect CLAUDE.md changes across sessions? Hash the content if it appears in the logs, or correlate with git history of the CLAUDE.md file if the project path is known
- [Affects R5] Which 10 techniques are "essential"? Candidates: thinking block divergence, survival analysis, entropy rate, tool sequence mining, ecology diversity, HSMM, information foraging, lag sequential, change-point detection, SPC. Needs prioritization based on runtime vs. value
- [Affects R2][Needs research] What are the exact JSONL schemas for Codex CLI, Gemini CLI, Cursor, and OpenCode? We have Claude Code and OpenClaw schemas from the research. Others need investigation
- [Affects R6][Technical] Minimum `uv` version required? Does `uv` work reliably on all target platforms?
- [Affects R8][Technical] Optimal data exchange format between Rust and Python subprocesses — JSON for small data, Parquet for large tables, or always one format?
- [Affects R9][Needs research] Which Vega-Lite chart types best represent each technique's output? Survival curves, control charts, heatmaps, network graphs each need specific specs

## Next Steps

→ `/ce:plan` for structured implementation planning
