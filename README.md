# Third Thoughts

A Lightless Labs research project studying AI agent behavior at scale through multi-disciplinary corpus analysis (basically, throwing stuff at the wall and seeing what sticks).

Named after Tiffany Aching's concept from Discworld: *first thoughts* (agents thinking), *second thoughts* (agents analyzing their thinking), *third thoughts* (this project analyzing **that**).

## What's in this repo

Third Thoughts has two halves that share a corpus and a methodology:

1. **`middens/`** — a Rust CLI for extracting behavioral patterns from AI agent session logs. Parses transcripts from Claude Code, Codex, and OpenClaw (Gemini stub), classifies messages and sessions, and runs a battery of 23 analytical techniques (6 Rust-native + 17 Python, bundled via an embedded Python bridge). The CLI has three core commands: `analyze` (run techniques → Parquet storage), `interpret` (LLM-powered cross-technique narrative), and `export` (Jupyter notebook). See [`middens/README.md`](middens/README.md).
2. **Research artifacts** — methods catalog, natural-language specs, replication studies, and documented findings in `docs/`. This is where the scientific claims live.

The corpus itself (`corpus/`, `experiments/`) is gitignored — the sessions contain private data and cannot be redistributed. The tooling and methodology are open; the raw data is not.

## Headline findings

| Finding | Status | Scope |
|---------|--------|-------|
| 100% risk-token suppression in paired thinking/text messages | Provisional | `language=en ∧ thinking_visibility=Visible ∧ ¬contaminated_by_Boucle`. N=828 sessions, 4,819 risk tokens, 209 paired messages. |
| HSMM pre-failure state (24.6× lift) | Robust (mixed corpus) | Pending re-run under 4-axis stratification. |
| MVT violated — agents under-explore | Robust | See `experiments/full-corpus/information-foraging.md`. |
| Session degradation (agents get worse over time) | Holds on interactive only | See `experiments/interactive/survival_analysis.txt`. |
| W10–W12 Boucle contamination in "interactive" bucket | Confirmed | 1,820/1,826 sessions carry autonomous-loop markers. |

**Compound scoping rule:** any headline finding on thinking or text behaviour must survive four axes — `session_type`, `thinking_visibility`, `language`, and a temporal window. A finding that doesn't survive all four is not a finding. More context in `CLAUDE.md` and `docs/HANDOFF.md`.

## Repository layout

```
middens/              Rust CLI — parser, classifiers, techniques, Python bridge
docs/
  HANDOFF.md          Session-continuity document, read this first
  methods-catalog.md  20 method families, 80+ references
  examples/           Worked examples for the CLI triad workflow
  nlspecs/            Natural-language specs (Why / What / How / Done)
  reports/            Research reports
  reviews/            Multi-model peer reviews
  brainstorms/        Requirements docs
  plans/              Implementation plans
  solutions/          Institutional knowledge — documented learnings
scripts/              Python analytical battery (26 scripts, mostly superseded by middens)
todos/                Individual todo files with YAML frontmatter
```

Gitignored: `corpus/`, `corpus-full/`, `corpus-split/`, `corpus-frozen/`, `experiments/`, `data/labeled-messages.json`.

## Getting started

Install the CLI with Homebrew:

```bash
brew install lightless-labs/tap/middens
middens --help
```

`middens` currently ships binaries for Apple Silicon macOS, x86_64 Linux, and arm64 Linux. Homebrew is the easiest path; release tarballs and source builds are documented in [`middens/README.md`](middens/README.md).

If you want to run the CLI on your own session logs, head to [`middens/`](middens/). If you want to read about the methodology and findings, start with `docs/methods-catalog.md` and the reports under `docs/reports/`.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).
