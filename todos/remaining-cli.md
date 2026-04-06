# Remaining CLI Work

> **Note:** `fingerprint`, `report`, Parquet export, and Vega-Lite figure specs are **superseded** by the output-contract reshape. See `todos/output-contract.md` and `docs/design/output-contract.md`. They remain listed here with their new framing for reference.

## Commands
- [ ] **`middens fingerprint`** — *Superseded.* Reframed as a technique (subject fingerprint) + a technique (evolution diff) reading from storage. Analyzer fingerprint is absorbed into `manifest.json`. See `todos/output-contract.md` § "Fingerprint as a technique (retrofit)".
- [ ] **`middens report`** — *Superseded.* New contract: `(run_id, format) → view file`. Reads storage (Parquet + manifest), renders a view. No ambiguous "cross-technique synthesis". See `todos/output-contract.md` § "`middens report` command".

## Output Formats
- [ ] **Parquet export** — *Superseded.* Parquet becomes the *canonical storage layer*, not an alternate output format. See `todos/output-contract.md` § "Storage layer".
- [ ] **Vega-Lite figure specs** — *Superseded.* Vega-Lite becomes a `FigureKind` variant embedded inside views (notebook, HTML), not a top-level output format. See `todos/output-contract.md` § "View layer" and the `FigureSpec` schema note.

## Pipeline Improvements
- [ ] **Progress reporting** — Show per-technique progress during `analyze` runs (technique name, elapsed time, ETA)
- [ ] **Parallel technique execution** — Run techniques concurrently via `std::thread::scope`. Currently sequential
- [ ] **Config file** — `~/.config/middens/config.toml` for default corpus path, technique selection, Python location, output format preferences

## Parsers
See `todos/additional-parsers.md`: OpenCode, Cursor, Gemini CLI full, Aider
