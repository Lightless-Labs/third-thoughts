# Middens Output Contract

**Status:** Design note (not yet implemented)
**Authors:** session 2026-04-06
**Related:** `todos/remaining-cli.md`, `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md`
**Blocked by:** Batch 3 Python technique ports

## Why this document exists

`middens analyze` currently emits markdown, JSON, and ASCII views in one pass, with `figures` as an unused slot on `TechniqueResult` and `middens report` as a stub. As we started planning Batch 3 we surfaced a better output model. This doc captures the decision so it isn't relearned next session.

## The core idea

**Middens output is a reproducible notebook backed by columnar storage.**

Two layers, cleanly separated:

1. **Storage layer — canonical, write-once per `analyze` run.** One format: Parquet for tabular data, plus a `manifest.json` holding run metadata, scalar findings, and prose summaries. Everything persistent lives here. If you lose the views, you rebuild them in seconds; if you lose storage, the run is gone.

2. **View layer — derived, regeneratable, multi-format.** Any number of renderers (`.ipynb`, `.md`, `.json`, `.html`, Pluto, Quarto, Typst, ...) read from storage and produce a view. Views are cheap functions of storage.

The reproducibility boundary is the storage layer. Views are throwaway.

## Why notebooks as the primary human view

Jupyter `.ipynb` (and peers like Pluto, Quarto) are the de facto gold standard for exploratory data science and research communication. They combine narrative prose, code, tables, and figures in a single linear artifact that's both human-readable and machine-executable.

Adopting `.ipynb` as a view format gives us:

- **Universal rendering**: GitHub, VS Code, JupyterLab, Colab, nbviewer, Deepnote all open `.ipynb` natively. No custom UI to build.
- **Pre-executed outputs**: the file ships with cached tables/figures, so static viewers (GitHub, plain browsers) show the full report without running anything.
- **Re-executable on demand**: a reader in JupyterLab or VS Code can hit "Run" on any cell to re-render with different parameters, drill into the underlying data, or change a chart — without middens being involved.
- **Self-describing**: each technique becomes a cell (prose summary + findings + tables + figures + a code cell that loads the sidecar Parquet for exploration).

**What we borrow from notebooks and what we reject:**

| Notebook property | Borrow? | Why / why not |
|---|---|---|
| Narrative + code + output in one artifact | Yes | Core value |
| Pre-executed cached outputs | Yes | Makes static viewing work |
| Arbitrary execution order / hidden state | **No** | Middens is a deterministic pipeline |
| `pip install` drift | **No** | Middens uses `uv` with pinned `requirements.txt` |
| Poor git diffs from embedded outputs | **Mitigated** | Sidecar Parquet files carry the volume; notebook stays small |
| Untested cells | **No** | Techniques have Cucumber coverage before they ship |

The framing: **"a notebook without the footguns."**

## Architecture

### Storage (`src/storage/`)

```
results/run-2026-04-06-<hash>/
    manifest.json              # run metadata + scalar findings + prose
    data/
        hsmm.parquet           # one parquet per technique, columnar tables
        information_foraging.parquet
        lag_sequential.parquet
        ...
```

**`manifest.json` schema (sketch):**

```json
{
    "run_id": "run-2026-04-06-ab3f12",
    "created_at": "2026-04-06T17:22:01Z",
    "analyzer_fingerprint": {
        "middens_version": "0.5.0",
        "git_sha": "fe3033d",
        "technique_versions": {"hsmm": "1.2.0", ...},
        "python_bridge": {"uv_version": "...", "requirements_hash": "..."}
    },
    "corpus_fingerprint": {
        "manifest_hash": "...",
        "session_count": 2594,
        "source_paths": ["..."]
    },
    "techniques": [
        {
            "name": "hsmm",
            "summary": "...",
            "findings": [{"label": "pre_failure_lift", "value": 24.6, ...}],
            "tables": [
                {"name": "State Transitions", "parquet": "data/hsmm.parquet", "table_key": "state_transitions"}
            ],
            "figures": [
                {"kind": "vega_lite", "spec_key": "state_heatmap", "caption": "..."}
            ]
        }
    ]
}
```

Scalar findings live directly in the manifest because they're cheap and nice to query without loading Parquet. Tables live in Parquet files, referenced by key. Figures are specs (Vega-Lite JSON, or base64 PNG, or a Parquet-reference for "plot this table"), not pre-rendered bitmaps — the view renderer decides how to embed them.

### View (`src/view/` — renamed from `src/output/`)

```rust
trait ViewRenderer {
    fn name(&self) -> &str;         // "ipynb", "html", "md", "json", "pluto", ...
    fn extension(&self) -> &str;
    fn render(&self, run: &AnalysisRun) -> Result<Vec<u8>>;
}
```

`AnalysisRun` is a storage reader that lazily loads manifest + Parquet. Every renderer gets the same input; implementations differ. Existing `markdown.rs`, `json.rs`, `ascii.rs` become `ViewRenderer` impls — mechanical rename, no logic change.

New renderers drop in: `ipynb.rs`, `html.rs`, `pluto.rs`, `quarto.rs`, etc.

## Command shape

```
middens analyze corpus/ -o results/run-2026-04-06/
    → writes storage (Parquet + manifest) + default view (markdown) for ergonomics
    → manifest includes run_id

middens report <run_id-or-path> --format ipynb
middens report <run_id-or-path> --format html
middens report <run_id-or-path> --format json
middens report <run_id-or-path> --format pluto       # Julia Pluto.jl
middens report <run_id-or-path> --format quarto      # Quarto .qmd
middens report <run_id-or-path> --format typst       # Typst doc

middens runs list                                     # discover past runs
```

**`middens report` contract:** `(run_id, format) → view file`. It renders *the* report for analysis run X in format Y. No ambiguity about what "cross-technique synthesis" means — the synthesis happens at analyze time into storage; report renders storage into a format.

### Run addressing

A run is addressed by its output directory OR by a run ID. A shallow registry (maybe `~/.local/share/middens/runs.json`, or just scan a conventional dir) maps run IDs → paths. Users stop needing to remember output paths. `middens runs list` shows past runs with timestamps, corpus hashes, and technique counts.

## Table schema constraints

To make Parquet round-trip (and by extension, notebook dataframe previews) work cleanly:

1. **Type-homogeneous columns.** No mixing ints and `"N/A"` strings in the same column. Use `null` for missing values.
2. **Optional `column_types`** on `Table`: `Option<Vec<ColumnType>>` where `ColumnType ∈ {Int, Float, String, Bool, Timestamp}`. Backwards-compatible — renderers that care (Parquet, ipynb) use it; markdown/JSON ignore. Techniques that don't specify get inferred types.
3. **No PII in cells.** No raw user/assistant text, no file paths, no `cwd` values, no tool-call arguments, no filenames. Permitted: derived numerics, tool-name symbols, parser-assigned stable session IDs (hash/UUID from the parser, never a filesystem path), ISO timestamps. This is a hard rule for all techniques, retroactive to Batches 1+2 (audit needed before reshape).

## Where findings, conclusions, and tables live

There are four distinct kinds of content and they don't all want the same storage:

| Content kind | Shape | Storage location | Why |
|---|---|---|---|
| **Prose summary** (per technique) | 2–3 sentences, markdown | `manifest.json` as a string field | Small, always read together with metadata, nice to `jq` without loading Parquet |
| **Scalar findings** (per technique) | `{label, value, description}` objects — scalars only | `manifest.json` as an array under each technique | Cheap to query/compare across runs, no columnar benefit |
| **Tables** (per technique) | Columnar, potentially many rows | `data/<technique>.parquet` — one file per technique, one row-group per table, `table_key` in the filename or as a Parquet schema field | Columnar format earns its keep only at volume; also the format pandas/polars/DuckDB all consume natively |
| **Figure specs** (per technique) | Vega-Lite JSON, base64 PNG, or table-reference | `manifest.json` inline when small (Vega-Lite specs usually <10KB); sidecar file in `figures/` only if a PNG exceeds, say, 100KB | Avoids a second roundtrip for small specs; keeps the manifest the single source of scalar truth |

**Conclusions** (a category we haven't formally had until now) are *cross-technique narrative* — "HSMM plus Smith-Waterman plus lag-sequential converge on X." They are **not produced by `analyze`** because techniques run independently and middens doesn't do synthesis at technique time. They live in one of two places depending on who writes them:

- **Analyst-authored conclusions**: a separate `conclusions.md` dropped into the run directory after the fact, and referenced from `manifest.json` via `conclusions_ref: "conclusions.md"`. Rendering views pick it up and place it at the top of the report.
- **LLM-authored conclusions** (future): a `middens synthesize <run_id>` command that reads storage, prompts a model, writes `conclusions.md`, and updates the manifest pointer. Entirely optional, entirely separate from `analyze`/`report`.

In both cases conclusions are *post-hoc annotation over frozen storage*, not baked into analyze.

**Rule of thumb for the manifest:** anything you might want to compare across runs without loading Parquet (e.g., "did `pre_failure_lift` go up since last week?") lives in the manifest. Anything row-shaped lives in Parquet. Anything narrative and bounded (prose summary) lives in the manifest. Anything narrative and unbounded (conclusions) lives in a sidecar `.md` referenced from the manifest.

## Figures

`FigureSpec` stops being an empty slot. It becomes:

```rust
enum FigureKind {
    VegaLite(serde_json::Value),      // JSON spec; renderers embed natively
    Png { data: Vec<u8>, encoding: "base64" },
    TableRef { table_key: String, chart_type: ChartType },  // "plot this table as a line chart"
}

enum ChartType {
    Line,       // time-series, trend lines (e.g., SPC series)
    Bar,        // categorical counts (e.g., tool frequencies)
    Heatmap,    // matrix views (e.g., Markov transitions, NCD matrix)
    Scatter,    // 2-axis point clouds (e.g., foraging distance vs yield)
    Histogram,  // distributional summaries (e.g., entropy)
    Boxplot,    // grouped distribution comparisons (e.g., low vs high correction)
}
```

The view renderer resolves a `TableRef` to the named Parquet table, picks reasonable axes from column types + a small hint map (e.g., `Line` defaults to first numeric column as y, session_index/timestamp as x), and emits the renderer-native chart object (Vega-Lite JSON in notebooks/HTML, matplotlib in Pluto, etc.). Techniques that want tight control over the chart can always emit a `VegaLite(...)` spec instead.

- **Vega-Lite** is the preferred format — interactive in JupyterLab/VS Code, renders in HTML, embeds in `.ipynb` as a `display_data` output, degrades to a JSON block in markdown.
- **PNG** is an escape hatch for matplotlib/other renderers that can't emit Vega-Lite.
- **TableRef** delegates chart construction to the view renderer — useful for simple "just plot this column over this column" cases where the technique shouldn't care about chart DSLs.

Vega-Lite is **not** a top-level output format; it lives inside views.

## What is *not* changing

- All 14 existing techniques (6 Rust + 8 Python from Batches 1+2)
- Python bridge (`UvManager`, `PythonTechnique`)
- Parsers, classifiers, corpus discovery, `analyze` pipeline orchestration
- 240 Cucumber scenarios
- `Session`, `TechniqueResult`, `Finding` types (aside from the optional `column_types` addition)
- The default view emitted by `analyze` stays markdown for ergonomics

## Why `analyze` still runs the techniques (not `report`)

`analyze` does the expensive work: parse corpus, classify, run all techniques, write storage. Techniques only run once per corpus. `report` is cheap and idempotent — it reads existing storage and renders a view. Re-rendering after a renderer bug fix doesn't re-run techniques. Trying a new format doesn't re-run techniques. This is the whole point of the storage/view split.

A run-once-per-corpus model also means `analyze` can parallelize techniques (currently sequential — see `todos/remaining-cli.md`) without affecting the view side.

## Sequencing

This design is **deferred until after Batch 3 ships**, to avoid ballooning scope mid-batch.

1. ✅ Batch 3 NLSpec amended for type-homogeneous columns, PII constraint, series tables on SPC — done during the discussion that produced this doc
2. (in progress) Dispatch red/green for Batch 3 against the current NLSpec
3. Batch 3 lands on `main`
4. Audit Batches 1+2 tables for type homogeneity and PII leakage (small fixes expected, possibly zero)
5. Add optional `column_types` to `Table` — backwards-compatible
6. Implement `src/storage/` (Parquet writer, manifest writer/reader)
7. Rename `src/output/` → `src/view/`, refactor renderers to `ViewRenderer` trait reading from storage
8. Implement `.ipynb` renderer
9. Wire `middens report <run_id> --format <fmt>` and `middens runs list`
10. Follow-up renderers: HTML, Pluto, Quarto as demand appears

Steps 6–9 can be a single PR or split by concern. None of it requires changes to technique code.

## Open questions

- **Run ID format**: timestamp + corpus hash (`run-2026-04-06-ab3f12`) vs UUID vs user-supplied label. Probably the first — human-readable and stable.
- **Where to store the run registry**: `~/.local/share/middens/runs.json` (XDG) vs scanning a conventional results dir vs both. Probably both — scan a default dir, optionally augment with an index.
- **Parquet library**: `polars` vs `arrow2`. Polars is heavier but more ergonomic; arrow2 is leaner. Decide at implementation time based on build-size budget.
- **Pre-executed notebook outputs**: embed directly in the `.ipynb` JSON (self-contained, no Python needed at render time) vs run `jupyter nbconvert --execute` as a post-step (adds a Python dep on the analyzer side). Embedding directly is cleaner — the Rust side writes outputs into the notebook JSON at generation time.
- **Diffing runs**: a future `middens diff run-A run-B` comparing manifests + Parquet is meaningful because storage is canonical. Not in scope now but worth keeping the door open — the manifest schema should make it feasible.

## Side-effect: `middens fingerprint`

Earlier in the session we documented `fingerprint` as having two layers:
- Subject fingerprint (per analyzed session): model, cwd, MCP servers, etc., harvested from session logs
- Analyzer fingerprint (the middens run itself): version, SHA, technique versions, corpus hash

The analyzer fingerprint *is* part of `manifest.json` in this design. So `fingerprint` as a standalone command becomes: "extract subject fingerprints from sessions and store them as a technique result" — it becomes just another technique that writes to Parquet. `evolution.rs` (diff fingerprints over time) becomes a second technique that reads those results. See `todos/remaining-cli.md`.
