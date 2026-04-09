---
date: 2026-04-09
topic: middens-cli-triad-analyze-interpret-export
source_docs:
  - docs/design/output-contract.md
  - todos/output-contract.md
  - todos/conclusions-v1-manual.md
  - todos/conclusions-v2-synthesize.md
status: draft
---

# Middens CLI Triad — analyze / interpret / export

## 1. Why

### 1.1 Problem Statement

`middens` today runs techniques and emits markdown / JSON / ASCII in a single pass inside `analyze`. Views are computed in memory and thrown away; there's no canonical storage, no cross-technique narrative, no notebook output, and `report` / `fingerprint` are stubs. Scaling past "one user, one corpus, one markdown file" needs:

1. **Canonical storage** that's query-friendly and round-trips cleanly into data-science tooling (notebooks, DuckDB, pandas, polars).
2. **Post-hoc narrative** written over frozen storage — "here's what all the techniques say together" — without entangling it with technique execution.
3. **Multi-format presentation** derived from storage, with Jupyter as the primary human view.

The design has been worked out in `docs/design/output-contract.md`. This NLSpec is the **integration spec** for the three-command triad that delivers it.

### 1.2 Design Principles

- **Storage is canonical, views are throwaway.** Every presentation format is a pure function of storage. Losing a view costs seconds to rebuild; losing storage loses the run.
- **Each command does one thing.** `analyze` computes, `interpret` narrates, `export` renders. No command crosses boundaries.
- **Sane defaults, explicit overrides.** All three commands work with zero flags against the most recent matching run under a predictable XDG path. Flags override, they don't have to be set.
- **Fail loudly when a prerequisite is missing.** If no LLM CLI is on `PATH`, or the chosen one is unauthenticated, say so. Don't fake it and don't silently skip.
- **No SDK dependency for `interpret`.** Piggyback on existing CLI tooling (`claude`, `codex`, `gemini`) via subprocess. Matches how this project already delegates model work.
- **Idempotent and reproducible.** Same inputs → same Parquet bytes (modulo timestamps isolated to the manifest). Same analysis + same prompt → same conclusions (modulo model nondeterminism).

### 1.3 Layering and Scope

The triad covers:

- A new `src/storage/` module (Parquet writer/reader + `manifest.json` writer/reader + `AnalysisRun` reader type)
- A rename of `src/output/` → `src/view/` and a `ViewRenderer` trait reading from `AnalysisRun`
- An `.ipynb` renderer (v4 nbformat, no Python dep at render time)
- New `interpret` and `export` subcommands in `main.rs`
- A reshape of the existing `analyze` subcommand to emit storage + default view
- Default-path UX: latest-matching-run discovery under `~/.local/share/com.lightless-labs.third-thoughts/`
- Provider fallback for `interpret`: `which`-based detection of `claude` / `codex` / `gemini`

**Out of scope for this milestone (each has a dedicated todo):**

- Fingerprint retrofit (`todos/fingerprint-technique-retrofit.md`)
- `corpus-timeline` deletion (`todos/corpus-timeline-deletion.md`)
- PII + type-homogeneity audit of Batches 1+2 (`todos/batches-1-2-pii-and-type-audit.md`)
- HTML / Pluto / Quarto / Typst renderers — only `.ipynb` is required for v1
- `middens diff` cross-run comparison
- `middens runs list` registry — scan-only-at-default-dir UX is acceptable for v1
- PNG figure embedding — Vega-Lite only for v1; techniques that currently emit no figures stay figure-less
- Autonomous session stratum, multilingual remediation, HSMM re-runs, GH#42796 follow-up

## 2. What

### 2.1 Storage paths

All storage lives under a single predictable XDG-compliant root:

```text
$XDG_DATA_HOME/com.lightless-labs.third-thoughts/
    analysis/
        run-<YYYY-MM-DD-HH-MM>-<short-corpus-hash>/
            manifest.json
            data/
                <technique_slug>.parquet
                ...
            sessions.parquet                # canonical sessions table
            default-view.md                 # ergonomic sidecar, regeneratable
    interpretation/
        <analysis-run-slug>/
            <YYYY-MM-DD-HH-MM>-<provider-slug>/
                manifest.json               # points back at analysis run
                conclusions.md              # overall cross-technique narrative
                <technique_slug>-conclusions.md
                ...
                prompt.md                   # exact prompt sent to the provider
```

If `$XDG_DATA_HOME` is unset, fall back to `~/.local/share/` per the XDG base-directory spec.

### 2.2 Run addressing and slug format

- **Analysis run ID:** `run-<YYYY-MM-DD-HH-MM>-<hash8>` where `hash8` is the first 8 hex chars of a stable corpus fingerprint (sorted session-id list hashed with SHA-256, or equivalent — reuse the `freeze` manifest hash if it exists). Multiple runs per day are supported by the `HH-MM` component.
- **Interpretation slug:** `<YYYY-MM-DD-HH-MM>-<provider-slug>` where `provider-slug ∈ {claude, codex, gemini}`. Multiple interpretations per analysis per day are supported by `HH-MM`.
- **Reference back:** the interpretation manifest carries `analysis_run_id` and an absolute path to the analysis dir it interprets.

### 2.3 Data model

```text
RECORD AnalysisManifest:
  run_id: String                         -- "run-2026-04-09-1432-ab3f12de"
  created_at: Timestamp
  analyzer_fingerprint:
    middens_version: String
    git_sha: Option<String>
    technique_versions: Map<String, String>
    python_bridge: Option<{uv_version, requirements_hash}>
  corpus_fingerprint:
    manifest_hash: String
    session_count: Int
    source_paths: List<String>           -- roots, not individual files
  techniques: List<TechniqueEntry>
  conclusions_ref: Option<String>        -- always None from analyze; interpret sets it
                                         -- (in the interpretation manifest, not the analysis one)

RECORD TechniqueEntry:
  name: String                           -- slug, stable
  version: String
  summary: String                        -- 2-3 sentence prose
  findings: List<Finding>                -- scalars only
  tables: List<TableRef>                 -- one ref per named table in the technique's parquet
  figures: List<FigureSpec>
  errors: List<String>                   -- per-technique errors; empty on success

RECORD TableRef:
  name: String                           -- "State Transitions"
  table_key: String                      -- e.g. "state_transitions"
  parquet: String                        -- "data/hsmm.parquet"
  row_count: Int
  column_types: Option<List<ColumnType>> -- from TechniqueResult if supplied

ENUM ColumnType: Int | Float | String | Bool | Timestamp

ENUM FigureKind:
  VegaLite(Value)                        -- JSON spec, embedded in manifest if <10KB
  TableRef { table_key, chart_type: ChartType }

ENUM ChartType: Line | Bar | Heatmap | Scatter | Histogram | Boxplot

RECORD InterpretationManifest:
  interpretation_id: String              -- "2026-04-09-1500-claude"
  created_at: Timestamp
  analysis_run_id: String
  analysis_run_path: String              -- absolute
  provider: String                       -- "claude" | "codex" | "gemini"
  model: Option<String>                  -- as reported by provider, if available
  prompt_hash: String                    -- sha256 of prompt.md
  template_version: String               -- embedded template version
  conclusions: ConclusionsIndex

RECORD ConclusionsIndex:
  overall: String                        -- "conclusions.md"
  per_technique: Map<String, String>     -- technique_slug -> "<slug>-conclusions.md"
```

### 2.4 Command surfaces

```text
middens analyze [CORPUS_PATH]
    [--output-dir DIR]                   -- default: $XDG_DATA_HOME/com.../analysis/<run-id>/
    [--techniques LIST]                  -- comma-separated technique slugs
    [--split]                            -- existing interactive/subagent stratification
    [--no-default-view]                  -- suppress default-view.md emission
    [--default-view FORMAT]              -- default: markdown

middens interpret
    [--analysis-dir DIR]                 -- default: latest under XDG analysis/
    [--provider PROVIDER]                -- default: auto via fallback chain
    [--model MODEL]                      -- optional, passed through to provider
    [--output-dir DIR]                   -- default: $XDG_DATA_HOME/com.../interpretation/<slug>/<HH-MM>-<provider>/
    [--dry-run]                          -- print prompt, skip provider call
    [--force]                            -- overwrite existing interpretation at same path

middens export
    [--analysis-dir DIR]                 -- default: latest under XDG analysis/
    [--interpretation-dir DIR]           -- default: latest matching, optional
    [--no-interpretation]                -- explicitly skip interpretation even if present
    [--format FORMAT]                    -- default: jupyter (only value supported in v1)
    [-o FILE]                            -- default: report.ipynb in cwd
```

### 2.5 Behavioural rules

**`analyze`:**

1. Runs the existing analysis pipeline (discover → parse → classify → techniques).
2. Generates `run_id` from the corpus fingerprint + current time (`HH-MM`).
3. Writes `manifest.json` + one Parquet file per technique under `data/` + a top-level `sessions.parquet` with the canonical sessions table.
4. Writes `default-view.md` unless `--no-default-view` is set. Default view is produced via the same `ViewRenderer` path that `export` uses — no shortcut from in-memory results to markdown.
5. On technique error: write the error into `TechniqueEntry.errors` and continue. Non-zero exit only if zero techniques succeeded.
6. Prints the run-id and storage path to stdout on success.

**`interpret`:**

1. Resolves `--analysis-dir` (or discovers the most-recently-modified run under the XDG analysis root).
2. Resolves `--provider`: explicit > fallback chain (`claude` → `codex` → `gemini` via `which`).
3. If the chosen provider is missing from `PATH`: fail with a clear message listing which providers were tried.
4. Builds the prompt from an embedded template, substituting manifest + per-technique summaries + scalar findings + top-N rows of headline tables.
5. Writes the prompt to `prompt.md` in the output dir **before** calling the provider.
6. Calls the provider as a subprocess: `claude -p "$(cat prompt.md)"` / `codex exec --skip-git-repo-check --full-auto -o conclusions.md "$(cat prompt.md)"` / `gemini -y -s false --prompt "$(cat prompt.md)"`. Exact invocation is templated per provider.
7. Parses the provider's response into: one overall `conclusions.md` + one `<technique_slug>-conclusions.md` per technique. The prompt must instruct the model to emit section markers (e.g., `<!-- technique: hsmm -->`) that the parser splits on.
8. Writes an `InterpretationManifest` referencing the analysis run.
9. On provider failure (non-zero exit, empty output, unparseable sections): fail loudly, leave `prompt.md` on disk for debugging, do not write a partial manifest.
10. Refuses to overwrite an existing interpretation at the same output path unless `--force`.
11. `--dry-run`: renders the prompt to `prompt.md` (under a `.dryrun/` subdir), skips provider call, exits 0.

**`export`:**

1. Resolves `--analysis-dir` (default: latest under XDG analysis root).
2. Resolves `--interpretation-dir` (default: latest matching under XDG interpretation/`<analysis-run-slug>`/; `--no-interpretation` forces skip).
3. Loads analysis via `AnalysisRun` reader; loads interpretation if present.
4. Renders a notebook via the `IpynbRenderer` impl of `ViewRenderer`.
5. Writes the output file (default: `report.ipynb` in cwd).
6. **Must succeed with analysis alone, no interpretation.** Tested as a first-class path.

**Default-path resolution:**

- "Latest" = most recently modified subdirectory matching the run-id glob. Ties broken by name-sort descending.
- If the XDG path doesn't exist: `analyze` creates it; `interpret` / `export` fail with a clear "no analysis runs found, run `middens analyze` first" message.

**Provider fallback:**

- Fallback chain: `claude` → `codex` → `gemini`, in that order.
- Detection: `which <name>` (or equivalent `PATH` walk). Success = executable found. No auth probing.
- If installed but unauthenticated, the subprocess call fails at step 6 of the interpret flow — let the provider's own error message surface.

### 2.6 What is *not* changing

- All 23 existing techniques (6 Rust + 17 Python from Batches 1–4)
- Python bridge (`UvManager`, `PythonTechnique`, embedded scripts)
- Parsers, classifiers, corpus discovery
- 270 Cucumber scenarios (new ones added, existing ones preserved)
- `Session`, `TechniqueResult`, `Finding` types (aside from optional `column_types` addition and expanded `FigureKind` enum)
- The `freeze` command and its manifest

## 3. How

### 3.1 Work breakdown (suggested PR boundary per group)

**Group A — storage layer foundation.**
1. Pick Parquet library (`polars` vs `arrow2`). Default to `polars` for ergonomics unless binary-size budget rules it out. Record the decision in the PR description.
2. Add `src/storage/mod.rs` with `Manifest`, `TableRef`, `FigureSpec`, `AnalysisRun` reader, `ManifestWriter`, `ParquetWriter`.
3. Add optional `column_types: Option<Vec<ColumnType>>` to `Table` in `src/techniques/mod.rs`. Backwards-compatible.
4. Expand `FigureKind` enum. Existing techniques pass `None`.
5. Cucumber: storage round-trip scenarios (write manifest + parquet, read back, assert equality).

**Group B — view layer rename + ipynb renderer.**
1. Rename `src/output/` → `src/view/`. Mechanical.
2. Convert existing `markdown.rs`, `json.rs`, `ascii.rs` to `ViewRenderer` impls consuming `AnalysisRun` instead of `&TechniqueResult`.
3. Add `src/view/ipynb.rs`. Writes v4 nbformat JSON directly (~200 lines). No Python dep.
4. Cell structure per technique: markdown cell (title + summary + findings) → code cell loading `pd.read_parquet` with pre-executed output showing head of the table → optional exploratory starter snippet.
5. Top-of-report cells: run metadata, corpus fingerprint, analyzer fingerprint, `conclusions.md` (inline) if present.
6. Cucumber: ipynb schema validity, cell-count invariants, conclusions injection on/off.

**Group C — `analyze` reshape.**
1. Update `src/pipeline.rs` to write storage via `src/storage/` instead of rendering markdown/json/ascii directly.
2. Generate `run_id`, compute corpus fingerprint (reuse `freeze` hash logic).
3. Emit `default-view.md` via the same `ViewRenderer` path `export` uses.
4. Update existing `analyze` Cucumber scenarios for the new output layout. Add scenarios asserting `manifest.json` + `data/*.parquet` presence.
5. Preserve `--split`, `--techniques`, `--no-default-view`, `--default-view` flags.

**Group D — `export` command.**
1. New `src/commands/export.rs`. Argument parsing, default-path resolution, `AnalysisRun` load, `IpynbRenderer::render`, file write.
2. Latest-matching-run discovery helper in `src/storage/` (scan XDG analysis/ dir, return most-recently-modified match).
3. Cucumber: export from explicit dir, export from default path, export without interpretation, export with interpretation, export fails with clear message when no analysis runs exist.

**Group E — `interpret` command.**
1. New `src/commands/interpret.rs`. Argument parsing, default-path resolution, provider detection, prompt build, subprocess call, response parse, manifest write.
2. Embedded prompt template at `src/commands/interpret/prompt-template.md` via `include_str!`. Template versioning via a `TEMPLATE_VERSION` constant.
3. Provider abstraction: `trait Provider { fn name() -> &str; fn cmdline(prompt_path: &Path) -> Command; }`. Three impls: `ClaudeProvider`, `CodexProvider`, `GeminiProvider`. `detect_provider(override: Option<&str>) -> Result<Box<dyn Provider>>` walks the fallback chain.
4. Response parser: splits on `<!-- technique: <slug> -->` markers, top-level content before first marker becomes `conclusions.md`.
5. Cucumber: dry-run produces prompt without calling provider; provider fallback picks first available; unknown provider override errors cleanly; parsing failure leaves `prompt.md` on disk; `--force` overwrite semantics.
6. Provider subprocess calls are stubbed in tests via a `MOCK_PROVIDER` env var that routes to a fixture script.

**Group F — wiring + docs.**
1. Update `main.rs` subcommand dispatch.
2. Update `README.md` and `middens/README.md` with the triad usage.
3. Update `docs/HANDOFF.md` with triad completion status.
4. Add a worked example under `docs/examples/` showing the end-to-end path: `analyze` → `interpret` → `export` → open the notebook.

### 3.2 Adversarial process

Non-trivial feature → full adversarial split:

1. Orchestrator writes this NLSpec.
2. Review pass (self or quick peer) before dispatch.
3. **Red team** (Gemini or Codex via `/gemini-cli` / `/codex-cli`) writes Cucumber `.feature` files from sections 1 + 2 + 6 (Done) only. Does not see the How. Flags contract gaps as blocking.
4. Orchestrator resolves contract gaps by amending the NLSpec — **not** by editing tests or code directly.
5. **Green team** (Kimi K2.5 via `/opencode-cli`, or per-group Claude subagent) implements from the How only, one group per dispatch. Does not see the `.feature` files.
6. Orchestrator routes per-scenario pass/fail back to green **without leaking test source**. When a scenario fails, diagnose: spec unclear → amend NLSpec; implementation wrong → reroute with description of the failing behaviour, not the assertion.
7. Iterate until all scenarios pass.

Group A (storage foundation) is the natural first dispatch since every other group depends on it.

### 3.3 Risks and mitigations

| Risk | Mitigation |
|---|---|
| Polars pulls in a huge dependency tree | Measure `cargo bloat` after Group A; fall back to `arrow2` if release-binary size jumps >5MB |
| Provider CLIs change invocation syntax | Each provider impl owns its command-line construction; the test suite mocks via `MOCK_PROVIDER` so real-CLI drift is caught only at integration test time, not unit test time |
| LLM doesn't emit clean section markers | Prompt template instructs explicit marker format; response parser fails loudly with a diagnostic if markers are missing, leaving `prompt.md` + raw response on disk |
| `default-view.md` double-rendering (analyze + export) produces different output | Enforced single-path: both go through `MarkdownRenderer::render(&AnalysisRun)`. Cucumber asserts byte-equality between analyze-emitted default-view and a fresh export |
| Notebook embedding precomputed outputs diverges from Parquet | Generation writes both from the same in-memory state; round-trip test loads the Parquet and asserts head-equality with the embedded output |
| Corpus fingerprint instability across platforms | Hash a sorted list of session IDs, not file paths or mtimes |

### 3.4 Dependencies to add

- Parquet library (`polars` or `arrow2`)
- `serde_json` (already in tree) — used for ipynb JSON output
- No new Python deps on the analyzer side: `.ipynb` is generated directly

## 4. Done

### 4.1 Acceptance scenarios (these become Cucumber `.feature` files)

#### Storage

1. **Round-trip a minimal analysis.** Given a fixture corpus with 2 sessions, when `analyze` runs, then `manifest.json` and at least one `data/*.parquet` file exist, the manifest validates against the schema, and `AnalysisRun::load` reads them back and returns a structure where technique count, table row counts, and scalar findings match what the pipeline computed in memory.
2. **Corpus fingerprint is stable.** Running `analyze` twice against the same corpus produces the same `corpus_fingerprint.manifest_hash` (modulo run_id/HH-MM).
3. **Type-homogeneous columns survive round-trip.** A technique that declares `column_types: [Int, Float, String]` produces a Parquet file whose schema matches, and loading it back preserves the types.
4. **PII-forbidden columns are rejected.** If a technique emits a table containing a column whose values include any of a known PII set (raw message text, absolute file paths), the writer fails loudly with a diagnostic naming the offending technique + column. *(Audit of existing techniques is out of scope; the writer-side check is in scope.)*

#### Analyze

5. **Analyze writes the expected layout.** `middens analyze <fixture>` produces `<run-dir>/manifest.json`, `<run-dir>/sessions.parquet`, `<run-dir>/data/*.parquet`, `<run-dir>/default-view.md`.
6. **Run ID format.** The run dir matches `^run-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{8}$`.
7. **Multiple runs same day.** Running `analyze` twice within the same minute produces two distinct run dirs. (Implementation note: include seconds in the collision path if minute-level collision happens, or append a `-1` suffix.)
8. **`--no-default-view` suppresses default view.** When set, `default-view.md` does not exist in the run dir.
9. **Default view equals a fresh export.** `cat <run>/default-view.md` is byte-equal to `middens export --analysis-dir <run> --format markdown --no-interpretation -o /dev/stdout` (once markdown is wired through `ViewRenderer`).
10. **Technique errors do not abort the run.** With a fixture that causes one technique to fail, `manifest.json` still exists, the failing technique's `errors` field is non-empty, and at least one other technique's output is present.
11. **Analyze default output dir is XDG.** With no `--output-dir`, runs land under `$XDG_DATA_HOME/com.lightless-labs.third-thoughts/analysis/`.

#### Interpret

12. **Default analysis discovery.** With a run already under the XDG analysis dir and no `--analysis-dir` given, `interpret` picks the most-recently-modified run.
13. **No analysis runs → clear error.** With an empty XDG analysis dir, `interpret` exits non-zero with a message containing `no analysis runs found`.
14. **Provider fallback picks first available.** With mocked `which` resolving `claude` only, `interpret` selects `claude`. With only `gemini` available, it selects `gemini`. With none available, it fails with a message listing all three.
15. **Explicit provider overrides fallback.** `--provider codex` with `codex` absent from `PATH` fails cleanly with a message naming `codex`.
16. **Dry-run writes prompt, skips provider.** `--dry-run` produces a `prompt.md` in a `.dryrun/` subdir and does not invoke the subprocess. Exit 0.
17. **Interpretation output layout.** On success, the interpretation dir contains `manifest.json`, `prompt.md`, `conclusions.md`, and one `<technique_slug>-conclusions.md` per technique present in the analysis.
18. **Interpretation manifest references analysis.** The interpretation `manifest.json` carries `analysis_run_id` and `analysis_run_path` matching the analysis it interpreted.
19. **Response parsing failure leaves debug artifacts.** With a mocked provider emitting output without section markers, `interpret` fails non-zero, `prompt.md` is on disk, a raw-response file is on disk, and no partial `manifest.json` is written.
20. **`--force` overwrites existing interpretation.** Without `--force`, a second `interpret` at the same output path fails. With `--force`, it overwrites.
21. **Interpretation slug format.** The interpretation subdir matches `^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-(claude|codex|gemini)$`.

#### Export

22. **Export with interpretation.** Given an analysis + an interpretation, `export --format jupyter -o report.ipynb` produces a file that validates as nbformat v4, contains a top-level conclusions cell with text from the overall `conclusions.md`, and contains per-technique cells each including the corresponding `<slug>-conclusions.md` text.
23. **Export without interpretation.** With `--no-interpretation` (or no interpretation present), the notebook still renders with all technique sections but no conclusions cells. Exit 0.
24. **Export default-path discovery.** With no flags, `export` resolves to the latest analysis and latest matching interpretation automatically. The produced notebook contains metadata fields naming both.
25. **Export with `--interpretation-dir` override.** Explicit flag wins over latest-matching discovery.
26. **Export fails cleanly on missing analysis.** Empty XDG analysis dir → non-zero exit, message contains `no analysis runs found`.
27. **Notebook embeds pre-executed outputs.** Per-technique code cells have non-empty `outputs` arrays containing a `display_data` entry whose pandas DataFrame preview shows the expected first row of the corresponding Parquet table.
28. **Notebook is self-contained.** Opening `report.ipynb` in a viewer that cannot execute Python still renders all tables, findings, and conclusions.

#### Integration

29. **End-to-end triad.** `analyze <fixture>` → `interpret` (with mocked provider) → `export` produces a notebook whose top cell names the analysis run ID, middle cells contain per-technique summaries + tables + interpretations, and the bottom cells expose exploratory starters.
30. **Idempotent re-export.** Running `export` twice in a row with the same analysis + interpretation produces byte-equal `.ipynb` files (modulo any timestamps, which must be pinned to the interpretation or analysis metadata, not generation time).

### 4.2 Definition of done

- [ ] All 30 acceptance scenarios pass under `cargo test`.
- [ ] `cargo build --release` succeeds with the chosen Parquet library.
- [ ] Release binary size increase documented in the PR description; `arrow2` fallback taken if polars adds >5MB.
- [ ] `middens analyze`, `middens interpret`, `middens export` all show up in `middens --help`.
- [ ] `middens --help` text for each command describes defaults and the XDG path.
- [ ] `docs/HANDOFF.md` updated: workstream 2 marked complete, current commit SHAs recorded, a worked example captured.
- [ ] `README.md` + `middens/README.md` reflect the triad command shape.
- [ ] No regression in the 270 existing Cucumber scenarios.
- [ ] Dry-run of `interpret` against a real analysis run produces a prompt that a human reviewer agrees "a model could answer this usefully" (manual step, not test-enforced).
- [ ] One live end-to-end run against a real corpus on at least one provider (`claude` preferred since it's what the user runs) — notebook opens in JupyterLab and is visually sensible.

## 5. Open questions

- **Parquet library choice.** Final decision belongs to Group A. Default recommendation: `polars`, fall back if binary bloats.
- **Notebook timestamp determinism.** Cell execution timestamps in `.ipynb` JSON — pin to a fixed value derived from the analysis `created_at`, or omit. Omitting is simpler.
- **Response parser marker convention.** `<!-- technique: <slug> -->` is a guess. May need iteration once real LLM output lands in dry-run testing.
- **Seconds in run IDs.** Minute-granularity was the user's ask. Sub-minute collision mitigation (append a `-1` suffix, or widen to HH-MM-SS) can be decided at implementation time; spec says minute.
- **Default-view format configurability.** `--default-view markdown` is the only value this milestone needs. Keep the flag but constrain to one value until more renderers land.
