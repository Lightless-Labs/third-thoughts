# middens

> *Middens (n.): archaeological refuse heaps. The discarded layers where past behavior leaves its most honest traces.*

A Rust CLI for extracting behavioral patterns from AI coding agent session logs. Part of the [Third Thoughts](https://github.com/Lightless-Labs/third-thoughts) research project.

Give it a directory of agent transcripts (Claude Code, Codex, OpenClaw), and it will parse, classify, and run a battery of 23 analytical techniques against them — Markov chains, entropy measures, HSMMs, survival analysis, change-point detection, convention epidemiology, and more.

> **Status: `0.0.1-beta.0`.** First public beta. Functional end-to-end on real corpora — but expect rough edges, incomplete privacy scrubbing in exports (see *Privacy notes* below), and a moving CLI surface. Available through Homebrew and GitHub Releases; not yet on crates.io.

## Install

### Homebrew (recommended)

```bash
brew install lightless-labs/tap/middens
middens --help
```

The Homebrew formula installs the published binary for supported platforms and recommends [`uv`](https://docs.astral.sh/uv/) so the Python-backed techniques work out of the box. If you really only want the Rust-native subset, `brew install lightless-labs/tap/middens --without-uv` works too.

Supported Homebrew targets: Apple Silicon macOS, x86_64 Linux, and arm64 Linux. Intel macOS is not in the initial binary matrix.

### From a GitHub Release

Grab the tarball for your platform from [Releases](https://github.com/Lightless-Labs/third-thoughts/releases) and extract it:

```bash
curl -LO https://github.com/Lightless-Labs/third-thoughts/releases/download/v0.0.1-beta.0/middens-0.0.1-beta.0-<target>.tar.gz
tar xzf middens-0.0.1-beta.0-<target>.tar.gz
cd middens-0.0.1-beta.0-<target>
./middens --help
```

Supported release targets: `aarch64-apple-darwin`, `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`. Windows and Intel macOS are planned-but-not-promised future stretch targets.

Verify the download against the release's `SHA256SUMS` file:

```bash
shasum -a 256 -c SHA256SUMS --ignore-missing
```

### From source

```bash
git clone https://github.com/Lightless-Labs/third-thoughts
cd third-thoughts/middens
cargo build --release --locked
./target/release/middens --help
```

Requires Rust 1.88+.

### Python-technique dependency

17 of the 23 techniques run in an embedded [`uv`](https://docs.astral.sh/uv/)-managed virtualenv. `uv` is a **runtime dependency** for the full battery — if it's not on `PATH`, middens degrades to the 6 Rust-native techniques and prints a warning. Homebrew installs `uv` by default as a recommended dependency. If you installed from a tarball or from source, install `uv` separately to unlock the full battery:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

The Python `requirements.txt` is baked into the binary and extracted to `$XDG_CONFIG_HOME/middens/python-assets/` on first run.

## The triad: analyze → interpret → export

Three core commands form a pipeline:

1. **`analyze`** — runs the technique battery, writes canonical storage (Parquet + manifest) to a predictable XDG path.
2. **`interpret`** — sends the analysis to an LLM runner (`claude`, `codex`, `gemini`, or `opencode`), which produces a cross-technique narrative with per-technique conclusions.
3. **`export`** — renders the analysis (and optional interpretation) as a Jupyter notebook.

Or `middens run` for the whole pipeline in one shot.

```bash
# 1. Analyze — compute everything, store results
middens analyze ~/.claude/projects/
# → run-0190e4b4-... written to ~/.local/share/com.lightless-labs.third-thoughts/analysis/

# 2. Interpret — ask an LLM to narrate the results
middens interpret
# → uses first available runner (claude-code → codex → gemini → opencode)
middens interpret --model codex/gpt-5.4-codex
# → explicit runner + model

# 3. Export — produce a Jupyter notebook
middens export
# → report.ipynb in cwd
middens export --no-interpretation
# → notebook without LLM conclusions

# Or: all three at once
middens run ~/.claude/projects/ --all --model claude-code/claude-opus-4-7 -o report.ipynb
```

All three commands use sane defaults — no flags required. They discover the latest run under `~/.local/share/com.lightless-labs.third-thoughts/` automatically. Flags override, they don't have to be set.

## Usage

```bash
# Full analytical battery on a corpus
middens analyze ~/.claude/projects/ -o results/

# Stratified by session type (interactive vs subagent)
# Unknown/autonomous sessions are excluded from both strata.
middens analyze path/ --split

# Run a subset of techniques
middens analyze path/ --techniques markov,entropy,thinking-divergence

# Parse a single file for debugging
middens parse file.jsonl

# Snapshot a corpus for reproducibility
middens freeze corpus/ -o manifest.json

# List all 23 techniques
middens list-techniques
```

## What it does

- **Parsers** — Claude Code, Codex, OpenClaw transcripts (Gemini is stubbed).
- **Classifiers** — 5-priority message classifier + session-type classifier (interactive / subagent / autonomous). The correction classifier checks for `tool_result` blocks before applying lexical patterns — the naive regex approach has a 90% false-positive rate on subagent sessions.
- **Techniques** — 6 Rust-native (Markov, entropy, thinking-divergence, survival, tool-diversity, correction-rate) + 17 Python (HSMM, SPC, NCD, ENA, convention epidemiology, lag-sequential, change-point detection, user-signal analysis, cross-project graph, and more).
- **Outputs** — Markdown, JSON, ASCII, Jupyter notebooks (`.ipynb`) via `export`.

Full technique catalog with academic references: [`../docs/methods-catalog.md`](../docs/methods-catalog.md).

## Methodological guardrails

Middens enforces a few rules the authors learned the hard way:

1. **Always stratify by session type.** Mixing interactive and subagent sessions produced statistics that moved from p=10⁻⁴² to p=0.40 on the same finding. Use `--split`. (Autonomous sessions are a third stratum under development — currently excluded from both `--split` populations rather than silently mixed in.)
2. **Thinking visibility matters.** The `redact-thinking-2026-02-12` header is UI-only — thinking still happens, it just isn't written to the transcript. Techniques that measure thinking content must be scoped to `thinking_visibility=Visible`.
3. **Language-invariant techniques only, unless explicitly scoped.** A handful of techniques (`thinking-divergence`, `correction-rate` priority-3, `user-signal-analysis`) are English-only and will emit a `skipped_non_english_messages` finding.

## Privacy notes

**Exports are not privacy-safe by default in this beta.** Analysis manifests, interpretation manifests, and the exported Jupyter notebooks may retain:

- absolute filesystem paths pointing at your home directory
- raw project identifiers (often repo / directory names)
- corpus source paths from your local machine

If you share a `report.ipynb` or the contents of `~/.local/share/com.lightless-labs.third-thoughts/`, **assume it contains PII** until we land the default-scrub pass in a subsequent release. Track progress in the repo's todos and `docs/HANDOFF.md`.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).
