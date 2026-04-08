# Output Contract: Storage / View Split

**Design doc:** `docs/design/output-contract.md`
**Status:** Deferred until Batch 3 Python techniques ship
**Created:** 2026-04-06

Reshape middens output from "analyze writes markdown/json/ascii in one pass" to **storage (Parquet + manifest) produced by `analyze`, views (ipynb/md/html/pluto/quarto/json) rendered by `report` from storage**.

Core idea: middens output is a *reproducible notebook backed by columnar storage*. Storage is the canonical, write-once artifact. Views are cheap regeneratable derivatives.

## Prereqs / ordering

- [ ] **Batch 3 lands on `main`** (NLSpec already aligned to the new table constraints; tasks #2–5 in session task list)
- [ ] **Audit Batches 1+2 for PII leakage** — no raw user/assistant text, no file paths, no cwd, no tool-call arguments, no filenames in any table cell. Permitted: derived numerics, tool-name symbols, parser-assigned stable session IDs, ISO timestamps. Expected finding count: low (techniques compute numerics), but do the audit.
- [ ] **Audit Batches 1+2 for type-homogeneous columns** — no mixing ints and `"N/A"` strings in the same column. Use `null` for missing. Fix sites found; probably <20 lines across 14 techniques.

## Schema additions (backwards-compatible)

- [ ] **Add optional `column_types: Option<Vec<ColumnType>>` to `Table`** in `middens/src/techniques/mod.rs`. `ColumnType ∈ {Int, Float, String, Bool, Timestamp}`. Renderers that care (Parquet, ipynb dataframe previews) use it; markdown/json/ascii ignore. Existing techniques keep working with `None`.
- [ ] **Expand `FigureSpec`** to `enum FigureKind { VegaLite(serde_json::Value), Png { data, encoding }, TableRef { table_key, chart_type } }`. Vega-Lite is preferred (interactive in JupyterLab/VS Code, degrades to fenced JSON in markdown).

## Storage layer (`src/storage/`)

- [ ] **`manifest.json` writer + reader** — carries run metadata, analyzer fingerprint (middens version, git SHA, technique versions, Python bridge versions), corpus fingerprint (manifest hash, session count), per-technique prose summaries and scalar findings, figure specs, and Parquet table refs. See `docs/design/output-contract.md` for sketch.
- [ ] **Parquet writer** — one file per technique, one row-group per table. Pick `polars` vs `arrow2` at implementation time based on build-size budget.
- [ ] **`AnalysisRun` storage reader** — lazily loads manifest + Parquet. Single input type that every view renderer consumes.
- [ ] **Content storage rules (enforced by writer):**
  - Prose summaries → `manifest.json` as strings
  - Scalar findings → `manifest.json` as arrays under each technique
  - Tables → `data/<technique>.parquet` referenced from manifest by `table_key`
  - Small figure specs (<10KB Vega-Lite JSON) → inline in manifest
  - Large PNGs (>100KB) → sidecar files in `figures/`, referenced from manifest
  - **Conclusions (cross-technique narrative)**: *not produced by analyze*. A post-hoc `conclusions.md` sidecar referenced from `manifest.json` via `conclusions_ref`. Analyst-authored or future `middens synthesize`-authored.

## View layer (rename `src/output/` → `src/view/`)

- [ ] **`ViewRenderer` trait** — `name()`, `extension()`, `render(&AnalysisRun) -> Result<Vec<u8>>`. Mechanical rename of existing renderers (markdown, json, ascii) into `ViewRenderer` impls reading from `AnalysisRun` instead of `&TechniqueResult`.
- [ ] **`Format` enum** — `{Markdown, Json, Ascii, Ipynb, Html, Pluto, Quarto, Typst, ...}`. Drives `--format` flag parsing.
- [ ] **Always-through-storage invariant** — even the default markdown view produced by `analyze` goes `techniques → TechniqueResult → storage → view`. One code path, no shortcut from in-memory results to views.

## `.ipynb` renderer

- [ ] **Write v4 nbformat JSON directly** — no Python dep, ~200 lines. Schema is stable and tiny.
- [ ] **Embed pre-executed outputs** — techniques already have summaries, findings, and tables computed. Write them into the notebook's `outputs` field at generation time so GitHub/static viewers show everything without re-execution.
- [ ] **Cell structure per technique** — markdown cell (title + summary + bulleted findings), code cell that loads the sidecar Parquet (`pd.read_parquet(...)`) with pre-executed output showing the headline table, optional code cell with an exploratory starter snippet the reader can tweak.
- [ ] **Figure embedding** — Vega-Lite → `display_data` cell with `application/vnd.vegalite.v5+json`. PNG → `display_data` with `image/png`. TableRef → fall back to "here's the data, here's a chart snippet using `altair`."
- [ ] **Top-of-report sections** — run metadata, analyzer + corpus fingerprints, `conclusions.md` inline if present.

## `middens report` command

- [ ] **`middens report <run_id_or_path> --format <fmt> [-o file]`** — reads storage, renders a view, writes file. Contract: `(run_id, format) → view file`. Clear, narrow, no synthesis ambiguity.
- [ ] **Run addressing by ID or path** — both `middens report run-2026-04-06-ab3f12 --format ipynb` and `middens report results/run-2026-04-06-ab3f12/ --format ipynb` work.
- [ ] **Default format** — markdown (matches the current `analyze` default) so users can omit `--format` for the common case.

## Run registry

- [ ] **`middens runs list`** — discover past runs, show `run_id`, timestamp, corpus hash, technique count, output path.
- [ ] **Registry location** — scan a conventional results dir (e.g., `./results/` or a configured default), optionally augmented with `~/.local/share/middens/runs.json` XDG index. Decide: scan-only vs scan+index.
- [ ] **Run ID format** — `run-<YYYY-MM-DD>-<short-corpus-hash>`. Human-readable, stable, sortable.

## `analyze` changes

- [ ] **`analyze` always writes storage** — Parquet + manifest, unconditionally.
- [ ] **`analyze` also writes default view** — markdown, for ergonomic continuity. Configurable via `--default-view <fmt>` or `--no-default-view`.
- [ ] **`analyze` generates `run_id`** and writes it into the manifest.

## Fingerprint as a technique (retrofit)

- [ ] **Reframe `middens fingerprint`** — the analyzer fingerprint is already in `manifest.json`. The subject fingerprint (per-session environment: model, cwd, MCP servers, CLAUDE.md hash, etc.) becomes a technique that writes its findings/tables to storage like any other.
- [ ] **`evolution.rs`** — becomes a second technique that reads fingerprint results and diffs them across time-ordered sessions, reporting drift.
- [ ] **Remove the standalone `fingerprint` command** — or keep as an alias that runs the fingerprint technique and renders just that slice.

## Follow-up renderers (incremental, drop in as demand appears)

- [ ] **HTML renderer** — self-contained HTML report with embedded Vega-Lite via CDN script tags. Useful for sharing without a notebook viewer.
- [ ] **Pluto.jl renderer** — Julia reactive notebook for users in the Julia data-science ecosystem.
- [ ] **Quarto renderer** — `.qmd` document, renders to HTML/PDF/docx via `quarto render`.
- [ ] **Typst renderer** — for publication-quality PDFs.

## Future: diffing runs

- [ ] **`middens diff run-A run-B`** — compare manifests + Parquet across runs. Report scalar-finding deltas, new/removed tables, table-row diffs for stable row keys, changed figure specs. Meaningful only because storage is canonical. Manifest schema should keep this path feasible (e.g., don't let timestamps leak into scalar findings in ways that make cross-run comparison noisy).

## Design questions still open

- [ ] **Parquet library decision** — `polars` vs `arrow2`. Polars: heavier, more ergonomic. Arrow2: leaner. Decide at implementation time.
- [ ] **Notebook output embedding** — embed pre-executed outputs directly in `.ipynb` JSON (self-contained, no Python dep) vs `jupyter nbconvert --execute` post-step (adds Python dep). Embedding directly is cleaner — default to that.
- [ ] **Run registry location** — scan-only, index-only, or both. Probably both.
- [ ] **Conclusions authorship** — analyst-written `conclusions.md` is the v1. `middens synthesize` (LLM-authored) is a possible future command but entirely separate from analyze/report.

## What does *not* change

- All 14 existing techniques (6 Rust + 8 Python from Batches 1+2 + 5 Python from Batch 3 once it lands)
- Python bridge (`UvManager`, `PythonTechnique`)
- Parsers, classifiers, corpus discovery, analyze pipeline orchestration
- 240 Cucumber scenarios
- `Session`, `TechniqueResult`, `Finding` types (aside from the optional `column_types` addition and the expanded `FigureKind` enum)

## Deprecates / replaces

- `middens report` stub (`src/report/`) — gets a real implementation under the new contract
- Parquet export todo in `todos/remaining-cli.md` — absorbed into the storage layer work here
- Vega-Lite figure specs todo in `todos/remaining-cli.md` — absorbed into `FigureKind::VegaLite` + ipynb renderer
- `middens fingerprint` stub — retrofitted as a technique

## Post-reshape cleanup

When the reshape lands, delete techniques that exist only because there is currently no canonical sessions table to query at view-render time:

- **`corpus-timeline`** (added in Batch 4 — see `todos/python-techniques-batch4.md`). Exists because reports must be reproducible without the source corpus, which forced (date, project, session_count) into a stored DataTable. Once `sessions.parquet` exists with `(session_id, project, started_at, ended_at, n_messages, …)`, `corpus-timeline` becomes a trivial GROUP BY at view-render time. Delete the technique, its embedded script, and its manifest entry; replace with a view spec. ~30-line cleanup.
