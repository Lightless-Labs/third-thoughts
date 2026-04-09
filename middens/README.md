# middens

> *Middens (n.): archaeological refuse heaps. The discarded layers where past behavior leaves its most honest traces.*

A Rust CLI for extracting behavioral patterns from AI coding agent session logs. Part of the [Third Thoughts](https://github.com/Lightless-Labs/third-thoughts) research project.

Give it a directory of agent transcripts (Claude Code, Codex, OpenClaw), and it will parse, classify, and run a battery of 23 analytical techniques against them — Markov chains, entropy measures, HSMMs, survival analysis, change-point detection, convention epidemiology, and more.

## Install

```bash
cargo install middens
```

Or build from source:

```bash
git clone https://github.com/Lightless-Labs/third-thoughts
cd third-thoughts/middens
cargo build --release
./target/release/middens --help
```

Python techniques (17 of the 23) run in an embedded `uv`-managed virtualenv. If `uv` isn't on your `PATH`, middens gracefully degrades to the 6 Rust-native techniques and prints a warning. Install uv from <https://docs.astral.sh/uv/>.

## Usage

```bash
# Full analytical battery on a corpus
middens analyze ~/.claude/projects/ -o results/

# Stratified by session type (interactive vs subagent vs autonomous)
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
- **Outputs** — Markdown, JSON, ASCII.
- **Embedded assets** — all Python scripts and the `requirements.txt` are baked into the binary via `include_str!` and extracted idempotently at runtime to `$XDG_CONFIG_HOME/middens/python-assets/`. The CLI is fully self-contained.

Full technique catalog with academic references: [`../docs/methods-catalog.md`](../docs/methods-catalog.md).

## Methodological guardrails

Middens enforces a few rules the authors learned the hard way:

1. **Always stratify by session type.** Mixing interactive and subagent sessions produced statistics that moved from p=10⁻⁴² to p=0.40 on the same finding. Use `--split`.
2. **Thinking visibility matters.** The `redact-thinking-2026-02-12` header is UI-only — thinking still happens, it just isn't written to the transcript. Techniques that measure thinking content must be scoped to `thinking_visibility=Visible`.
3. **Language-invariant techniques only, unless explicitly scoped.** A handful of techniques (`thinking-divergence`, `correction-rate` priority-3, `user-signal-analysis`) are English-only and will emit a `skipped_non_english_messages` finding.

## Status

0.1.0 — functional end-to-end on real corpora, not yet published to crates.io. See [`../docs/HANDOFF.md`](../docs/HANDOFF.md) for current implementation state and open work.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).
