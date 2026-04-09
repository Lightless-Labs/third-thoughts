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
- Runner fallback for `interpret`: `which`-based detection across `claude-code` / `codex` / `gemini` / `opencode`

**Out of scope for this milestone (each has a dedicated todo):**

- Fingerprint retrofit (`todos/fingerprint-technique-retrofit.md`)
- `corpus-timeline` deletion (`todos/corpus-timeline-deletion.md`)
- PII + type-homogeneity audit of Batches 1+2 (`todos/batches-1-2-pii-and-type-audit.md`)
- Markdown format on `export` (`todos/middens-export-markdown-format.md`)
- Overwrite UX for `export -o` (`todos/middens-export-overwrite-ux.md`)
- Response-parser strictness for `interpret` (`todos/interpret-parser-strictness.md`)
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
        run-<YYYY-MM-DD-HH-MM>-<uuidv7>/
            manifest.json
            data/
                <technique_slug>.parquet
                ...
            sessions.parquet                # canonical sessions table
            default-view.md                 # ergonomic sidecar, regeneratable
    interpretation/
        <analysis-run-slug>/
            <YYYY-MM-DD-HH-MM>-<runner-slug>-<uuidv7>/
                manifest.json               # points back at analysis run
                conclusions.md              # overall cross-technique narrative
                <technique_slug>-conclusions.md
                ...
                prompt.md                   # exact prompt sent to the runner
    interpretation-failures/
        <analysis-run-slug>/
            <YYYY-MM-DD-HH-MM>-<runner-slug>-<uuidv7>/
                prompt.md                   # prompt that was sent
                raw-response.txt            # whatever the runner emitted
                error.txt                   # parse diagnostic or stderr
```

If `$XDG_DATA_HOME` is unset, fall back to `~/.local/share/` per the XDG base-directory spec.

### 2.2 Run addressing and slug format

- **Analysis run ID:** `run-<YYYY-MM-DD-HH-MM>-<uuidv7>` where `<uuidv7>` is a canonical UUIDv7 string (RFC-9562). The `YYYY-MM-DD-HH-MM` prefix exists purely for human scanability in directory listings; the UUIDv7 guarantees uniqueness across arbitrarily-close invocations and is itself time-ordered, so sort-by-name still produces chronological order.
- **Interpretation slug:** `<YYYY-MM-DD-HH-MM>-<runner-slug>-<uuidv7>` where `runner-slug ∈ {claude-code, codex, gemini, opencode}`. Same rationale as above — UUIDv7 handles uniqueness, the timestamp prefix is ergonomic.
- **Corpus fingerprint:** SHA-256 of a newline-joined, lexicographically sorted list of parser-assigned session IDs from the corpus. First 8 hex chars become `corpus_fingerprint.short`, full hex becomes `corpus_fingerprint.manifest_hash`. The corpus fingerprint lives in the analysis manifest — it is **not** part of the run ID. This keeps run IDs independent of corpus identity and lets `analyze` on an empty or fingerprint-unstable corpus still succeed.
- **Reference back:** the interpretation manifest carries `analysis_run_id` and an absolute path to the analysis dir it interprets.

### 2.3 Data model

```text
RECORD AnalysisManifest:
  run_id: String                         -- "run-2026-04-09-14-32-0190e4b4-7e1c-7c4a-9f2b-5c9ab3f12de0"
  created_at: Timestamp
  analyzer_fingerprint:
    middens_version: String
    git_sha: Option<String>
    technique_versions: Map<String, String>
    python_bridge: Option<{uv_version, requirements_hash}>
  corpus_fingerprint:
    manifest_hash: String                -- full SHA-256 hex
    short: String                        -- first 8 hex chars, convenience
    session_count: Int
    source_paths: List<String>           -- roots, not individual files
  techniques: List<TechniqueEntry>

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
  interpretation_id: String              -- "2026-04-09-15-00-claude-code-0190e4b5-..."
  created_at: Timestamp
  analysis_run_id: String
  analysis_run_path: String              -- absolute
  runner: String                         -- "claude-code" | "codex" | "gemini" | "opencode"
  model_id: Option<String>               -- verbatim from --model <runner>/<model-id>
                                         -- None = let the runner pick its default
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
    [--model RUNNER/MODEL-ID]            -- default: auto via runner fallback chain
                                         -- format: <runner>/<model-id> where runner ∈
                                         -- {claude-code, codex, gemini, opencode} and
                                         -- model-id is free-form, passed verbatim to the runner.
                                         -- Examples:
                                         --   claude-code/claude-opus-4-6
                                         --   codex/gpt-5.4-codex
                                         --   gemini/gemini-3.1-pro-preview
                                         --   opencode/kimi-for-coding/k2p5
                                         --   opencode/zai-coding-plan/glm-5.1
                                         -- Parse rule: split on first '/' only;
                                         -- the remainder is model-id verbatim (may contain '/').
    [--output-dir DIR]                   -- default: $XDG_DATA_HOME/com.../interpretation/<analysis-run-slug>/<interpretation-slug>/
    [--dry-run]                          -- print prompt, skip runner call

middens export
    [--analysis-dir DIR]                 -- default: latest under XDG analysis/
    [--interpretation-dir DIR]           -- default: latest *valid* matching, optional
    [--no-interpretation]                -- explicitly skip interpretation even if present
    [--format FORMAT]                    -- default: jupyter (only value supported in v1)
    [-o FILE]                            -- default: report.ipynb in cwd (overwritten silently)
```

**Notes on `--model` parsing:**

The split-on-first-`/` rule is deliberate so OpenCode's native `<provider>/<model>` format passes through untouched. `opencode/kimi-for-coding/k2p5` → runner=`opencode`, model-id=`kimi-for-coding/k2p5`. Each runner adapter decides how its model-id maps to the runner's own CLI syntax (some use `--model`, some use `-m`, OpenCode uses `--model <provider>/<model>` verbatim). When `--model` is omitted, the runner is invoked with no explicit model flag — each runner picks its own native default. When the user supplies an unknown runner prefix, `interpret` fails with a message listing supported runners and pointing at the `--help` examples.

### 2.5 Behavioural rules

**`analyze`:**

1. Runs the existing analysis pipeline (discover → parse → classify → techniques).
2. Generates `run_id = "run-" + now().strftime("%Y-%m-%d-%H-%M") + "-" + uuidv7()`. Computes the corpus fingerprint and stores it in the manifest (not in the run ID).
3. Writes `manifest.json` + one Parquet file per technique under `data/` + a top-level `sessions.parquet` with the canonical sessions table.
4. **PII writer-side check.** Before writing any Parquet file, the writer validates each `Table` against a column blocklist and a value-length cap:
   - **Blocklisted column names** (case-insensitive substring match against the column name — no glob semantics): `path`, `file_path`, `filepath`, `cwd`, `text`, `content`, `message`, `filename`, `raw_`, `body`, `prompt`, `source`. The `raw_` entry is a literal substring and therefore catches `raw_data`, `raw_content`, `user_raw_text`, etc.
   - **Value-length cap:** no `String`-typed column value may exceed 200 characters.
   - On violation: fail loudly, naming the offending technique, table, column (or the offending cell's row index + column), and refuse to write the run. No partial output.
   - This is a writer-side invariant. Techniques are expected to produce derived numerics, not raw session content — the check exists to catch mistakes, not to sanitise real PII.
5. Writes `default-view.md` unless `--no-default-view` is set. Default view is produced via the same `ViewRenderer` path that `export` uses — no shortcut from in-memory results to markdown.
6. On technique error: write the error into `TechniqueEntry.errors` and continue. Non-zero exit only if zero techniques succeeded.
7. Prints the run-id and storage path to stdout on success.

**`interpret`:**

1. Resolves `--analysis-dir` (or discovers the most-recently-modified *valid* run under the XDG analysis root — valid = contains a parseable `manifest.json`).
2. Resolves runner from `--model`: the prefix before the first `/` is the runner slug. If `--model` is omitted, walks the fallback chain (`claude-code` → `codex` → `gemini` → `opencode`), picking the first whose binary is on `PATH` (`which`-based).
3. If the chosen runner is missing from `PATH`: fail with a clear message listing which runners were tried.
4. Allocates an interpretation slug `<YYYY-MM-DD-HH-MM>-<runner-slug>-<uuidv7>` and a **temp sibling directory** at the common parent of both possible final destinations: `$XDG_DATA_HOME/com.lightless-labs.third-thoughts/.tmp-<uuidv7>/`. Placing the temp dir at the common parent (rather than under `interpretation/` or `interpretation-failures/` directly) guarantees that the final `rename` call in step 8 stays on the same filesystem regardless of which destination is chosen, so the rename is atomic on every POSIX filesystem.
5. Builds the prompt from an embedded template, substituting manifest + per-technique summaries + scalar findings + **headline table excerpts**. Writes the prompt to `<tmp>/prompt.md` before any runner call.
   - **Headline table = the first `TableRef` in each `TechniqueEntry.tables`.** If the technique declares no tables, it contributes no excerpt. Each excerpt is the first **10** rows of the headline table, serialised as markdown.
6. Calls the runner as a subprocess. Each runner has an adapter that knows its CLI shape:
   - `claude-code` → `claude -p "$(cat prompt.md)"` (+ `--model <model-id>` if set)
   - `codex` → `codex exec --skip-git-repo-check --full-auto -o <tmp>/response.md "$(cat prompt.md)"` (+ `--model <model-id>` if set)
   - `gemini` → `gemini -y -s false --prompt "$(cat prompt.md)"` (+ `-m <model-id>` if set)
   - `opencode` → `opencode run --format json --model <model-id> "$(cat prompt.md)"` (model is mandatory for opencode; omitting `--model` for an opencode runner is an error)
7. Parses the runner's response into: one overall `conclusions.md` + one `<technique_slug>-conclusions.md` per technique. The prompt instructs the model to emit section markers `<!-- technique: <slug> -->`. The parser splits on those markers; content before the first marker becomes the overall `conclusions.md`.
8. Writes `manifest.json` into the temp dir, then **atomically renames** the temp dir to its final destination `<output-root>/interpretation/<analysis-run-slug>/<interpretation-slug>/`. Because the destination name contains a fresh UUIDv7, there is no possibility of collision and no need for `--force`.
9. **On any failure** (runner non-zero exit, empty output, unparseable sections, model-flag missing on opencode): move the temp dir from `.tmp-<uuidv7>/` to `<output-root>/interpretation-failures/<analysis-run-slug>/<interpretation-slug>/`, write an `error.txt` with the diagnostic, exit non-zero. The runner's own stderr is surfaced to the user's terminal — if the runner is installed-but-unauthenticated, that's what the user sees, and that is considered a correct outcome.
10. `--dry-run`: writes `prompt.md` into a new temp dir `.../interpretation-failures/<analysis-run-slug>/<interpretation-slug>/prompt.md` (same layout as a failed run, minus `response.txt`/`error.txt`), skips runner call, exits 0 with the prompt path printed to stdout.

**`export`:**

1. Resolves `--analysis-dir` (default: latest *valid* under the XDG analysis root).
2. Resolves `--interpretation-dir` (default: latest *valid* matching interpretation under `interpretation/<analysis-run-slug>/`; `--no-interpretation` forces skip). "Valid" = contains a parseable `manifest.json`. Failed interpretations under `interpretation-failures/` are never considered.
3. Loads analysis via `AnalysisRun` reader; loads interpretation if present.
4. Renders a notebook via the `IpynbRenderer` impl of `ViewRenderer`.
5. Writes the output file (default: `report.ipynb` in cwd, **silently overwriting** if it exists).
6. **Must succeed with analysis alone, no interpretation.** Tested as a first-class path.

**Default-path resolution:**

- "Latest valid" = scan the relevant XDG dir, keep only subdirectories matching the slug regex AND containing a parseable `manifest.json`, sort the survivors by directory name descending (UUIDv7 makes name-sort equivalent to time-sort), return the first.
- If the XDG path doesn't exist or contains no valid runs: `analyze` creates the path; `interpret` / `export` fail with `no analysis runs found, run 'middens analyze' first`.

**Runner detection:**

- Fallback chain order: `claude-code` → `codex` → `gemini` → `opencode`.
- Detection: `which <binary>` (or equivalent `PATH` walk). Success = executable found. No auth probing. Installed-but-unauthenticated surfaces via the runner's own stderr during step 6.

**`.ipynb` sub-contract** (for scenarios 24 + 27):

- Top-level `metadata.middens` object with keys: `analysis_run_id`, `analysis_run_path`, `interpretation_id` (optional — present only when an interpretation was loaded), `interpretation_path` (optional), `middens_version`.
- Per-technique code cells that load the technique's Parquet have pre-executed `outputs` arrays containing at least one `display_data` output with both `text/html` (pandas DataFrame HTML repr of the first 10 rows of the headline table) and `text/plain` (fallback) mime bundles.
- Cell `execution_count` values are pinned to sequential integers starting at 1. Timestamps inside notebook metadata are not generated at export time — if any timestamp is emitted, it is sourced from the analysis manifest's `created_at`, so repeated exports of the same analysis are byte-equal.

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
2. Generate `run_id = "run-" + now().strftime("%Y-%m-%d-%H-%M") + "-" + uuidv7()`. Compute corpus fingerprint as SHA-256 of newline-joined sorted session IDs; store in manifest only.
3. Emit `default-view.md` via the same `ViewRenderer` path `export` uses.
4. Update existing `analyze` Cucumber scenarios for the new output layout. Add scenarios asserting `manifest.json` + `data/*.parquet` presence.
5. Preserve `--split`, `--techniques`, `--no-default-view`, `--default-view` flags.

**Group D — `export` command.**
1. New `src/commands/export.rs`. Argument parsing, default-path resolution, `AnalysisRun` load, `IpynbRenderer::render`, file write.
2. Latest-matching-run discovery helper in `src/storage/` (scan XDG analysis/ dir, return most-recently-modified match).
3. Cucumber: export from explicit dir, export from default path, export without interpretation, export with interpretation, export fails with clear message when no analysis runs exist.

**Group E — `interpret` command.**
1. New `src/commands/interpret.rs`. Argument parsing, default-path resolution, runner detection, prompt build, temp-dir allocation, subprocess call, response parse, atomic rename.
2. Embedded prompt template at `src/commands/interpret/prompt-template.md` via `include_str!`. Template versioning via a `TEMPLATE_VERSION` constant.
3. Runner abstraction: `trait Runner { fn slug() -> &str; fn binary() -> &str; fn build_command(prompt_path: &Path, model_id: Option<&str>, work_dir: &Path) -> Result<Command>; }`. Four impls: `ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, `OpencodeRunner`. `parse_model_flag(&str) -> Result<(runner_slug, model_id)>` splits on first `/`. `detect_runner(override: Option<&str>) -> Result<Box<dyn Runner>>` walks the fallback chain.
4. Response parser: splits on `<!-- technique: <slug> -->` markers, top-level content before first marker becomes `conclusions.md`. **Strictness rules for missing/duplicate/unknown markers are deliberately left to a follow-up — see `todos/interpret-parser-strictness.md`.** v1 accepts whatever sections the model emits, at-most-one per slug, unknown slugs become their own files.
5. Atomic write: allocate temp dir at the common parent `<XDG>/com.lightless-labs.third-thoughts/.tmp-<uuidv7>/`, build everything inside it, on success `rename` to `<XDG>/com.../interpretation/<analysis-run-slug>/<slug>/`; on failure `rename` to `<XDG>/com.../interpretation-failures/<analysis-run-slug>/<slug>/`. The common-parent placement keeps `rename` on the same filesystem in both branches, which is the precondition for atomicity on every POSIX filesystem.
6. Cucumber: dry-run produces prompt without calling runner; fallback picks first available; unknown runner prefix errors cleanly; opencode without `--model` errors; response parsing failure moves artifacts to failures dir; model-flag-on-first-slash parsing.
7. Runner subprocess calls are stubbed in tests via a `MIDDENS_MOCK_RUNNER` env var that routes to a fixture script.

**Group F — wiring + docs.**
1. Update `main.rs` subcommand dispatch.
2. Update `README.md` and `middens/README.md` with the triad usage.
3. Update `docs/HANDOFF.md` with triad completion status.
4. Add a worked example under `docs/examples/` showing the end-to-end path: `analyze` → `interpret` → `export` → open the notebook.

### 3.2 Adversarial process

Non-trivial feature → full adversarial split:

1. Orchestrator writes this NLSpec.
2. Review pass (self or quick peer) before dispatch.
3. **Red team** (Gemini or Codex via `/gemini-cli` / `/codex-cli`) writes Cucumber `.feature` files from sections 1 + 2 + 4 (Done) only. Does not see the How (section 3). Flags contract gaps as blocking.
4. Orchestrator resolves contract gaps by amending the NLSpec — **not** by editing tests or code directly.
5. **Green team** (Kimi K2.5 via `/opencode-cli`, or per-group Claude subagent) implements from the How only, one group per dispatch. Does not see the `.feature` files.
6. Orchestrator routes per-scenario pass/fail back to green **without leaking test source**. When a scenario fails, diagnose: spec unclear → amend NLSpec; implementation wrong → reroute with description of the failing behaviour, not the assertion.
7. Iterate until all scenarios pass.

Group A (storage foundation) is the natural first dispatch since every other group depends on it.

### 3.3 Risks and mitigations

| Risk | Mitigation |
|---|---|
| Polars pulls in a huge dependency tree | Measure `cargo bloat` after Group A; fall back to `arrow2` if release-binary size jumps >5MB |
| Runner CLIs change invocation syntax | Each runner impl owns its command-line construction; the test suite mocks via `MIDDENS_MOCK_RUNNER` so real-CLI drift is caught only at integration test time, not unit test time |
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
2. **Corpus fingerprint is stable.** Running `analyze` twice against the same corpus produces the same `corpus_fingerprint.manifest_hash` and the same `corpus_fingerprint.short`; only the `run_id` (timestamp prefix + UUIDv7) differs between runs.
3. **Type-homogeneous columns survive round-trip.** A technique that declares `column_types: [Int, Float, String]` produces a Parquet file whose schema matches, and loading it back preserves the types.
4. **PII-blocklist column-name check.** A test technique that declares a column named `message` (or any name matching the blocklist from §2.5) causes `analyze` to fail loudly, name the offending technique + table + column in the error message, and leave no partial run directory on disk.
5. **PII value-length cap.** A test technique that emits a `String` column whose values exceed 200 characters causes `analyze` to fail with an error naming the technique, table, column, and the row index of the first offending cell. No partial output.

#### Analyze

6. **Analyze writes the expected layout.** `middens analyze <fixture>` produces `<run-dir>/manifest.json`, `<run-dir>/sessions.parquet`, `<run-dir>/data/*.parquet`, `<run-dir>/default-view.md`.
7. **Run ID format.** The run dir matches `^run-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (YYYY-MM-DD-HH-MM prefix + canonical UUIDv7).
8. **Multiple runs same minute.** Running `analyze` twice back-to-back within the same wall-clock minute produces two distinct run dirs. UUIDv7 in the run ID guarantees uniqueness.
9. **`--no-default-view` suppresses default view.** When set, `default-view.md` does not exist in the run dir.
10. **Default view is produced via the ViewRenderer path.** The `analyze`-emitted `default-view.md` is byte-equal to what `MarkdownRenderer::render(&AnalysisRun::load(<run>))` returns when invoked directly in a test. (This is a renderer-level byte-equality test, not a user-facing `export --format markdown` test — markdown export from the `export` command is deferred, see `todos/middens-export-markdown-format.md`.)
11. **Technique errors do not abort the run.** With a fixture that causes one technique to fail, `manifest.json` still exists, the failing technique's `errors` field is non-empty, and at least one other technique's output is present.
12. **Analyze default output dir is XDG.** With no `--output-dir`, runs land under `$XDG_DATA_HOME/com.lightless-labs.third-thoughts/analysis/`.

#### Interpret

13. **Default analysis discovery.** With a run already under the XDG analysis dir and no `--analysis-dir` given, `interpret` picks the most-recently-named *valid* run (sort run-dir names descending, first match with parseable `manifest.json`).
14. **Invalid analysis runs are skipped during discovery.** With two runs present, where the most-recently-named one has a corrupt `manifest.json`, `interpret` picks the older valid one instead.
15. **No analysis runs → clear error.** With an empty XDG analysis dir, `interpret` exits non-zero with a message containing `no analysis runs found`.
16. **Runner fallback picks first available.** With mocked `which` resolving `claude-code` only, `interpret` selects `claude-code`. With only `gemini` available, it selects `gemini`. With none of `{claude-code, codex, gemini, opencode}` available, it fails with a message listing all four.
17. **Explicit `--model` overrides fallback with runner prefix.** `--model codex/gpt-5.4-codex` with `codex` absent from `PATH` fails cleanly with a message naming `codex`.
18. **`--model` parses on first `/` only.** `--model opencode/kimi-for-coding/k2p5` resolves to runner=`opencode`, model-id=`kimi-for-coding/k2p5` (the second `/` is preserved). Captured in the interpretation manifest as `runner: "opencode"`, `model_id: "kimi-for-coding/k2p5"`.
19. **Unknown runner prefix fails with helpful error.** `--model foo/bar` exits non-zero with a message listing the four supported runner slugs.
20. **Dry-run writes prompt, skips runner.** `--dry-run` produces a `prompt.md` under `interpretation-failures/<analysis-run-slug>/<interpretation-slug>/`, prints its path to stdout, does not invoke any subprocess, and exits 0.
21. **Interpretation output layout on success.** The interpretation dir contains `manifest.json`, `prompt.md`, `conclusions.md`, and one `<technique_slug>-conclusions.md` per technique present in the analysis.
22. **Interpretation manifest references analysis.** The interpretation `manifest.json` carries `analysis_run_id` and `analysis_run_path` matching the analysis it interpreted, plus `runner` and `model_id`.
23. **Response parsing failure moves artifacts to failures dir.** With a mocked runner emitting output without section markers, `interpret` fails non-zero, the temp dir is moved to `interpretation-failures/<analysis-run-slug>/<slug>/` containing `prompt.md` + `raw-response.txt` + `error.txt`, and no directory appears under `interpretation/<analysis-run-slug>/`.
24. **Atomic write on success.** During a successful `interpret`, no directory exists at the final destination path until after the temp dir is fully written and manifest is serialised. (Test: inspect filesystem state mid-run via a pause hook.)
25. **Interpretation slug format.** The interpretation subdir matches `^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-(claude-code|codex|gemini|opencode)-[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`.
26. **OpenCode without `--model` is an error.** Running `interpret` with runner auto-detected to `opencode` (the only runner on PATH) but without `--model` fails with `opencode requires an explicit --model` because opencode's CLI has no native default.

#### Export

27. **Export with interpretation.** Given an analysis + an interpretation, `export --format jupyter -o report.ipynb` produces a file that validates as nbformat v4, contains a top-level conclusions cell with text from the overall `conclusions.md`, and contains per-technique cells each including the corresponding `<slug>-conclusions.md` text.
28. **Export without interpretation.** With `--no-interpretation` (or no interpretation present), the notebook still renders with all technique sections but no conclusions cells. Exit 0.
29. **Export default-path discovery.** With no flags, `export` resolves to the latest valid analysis and latest valid matching interpretation automatically. The produced notebook's `metadata.middens` object contains `analysis_run_id` + `analysis_run_path` matching the analysis, and `interpretation_id` + `interpretation_path` matching the interpretation.
30. **Export ignores failed interpretations.** With a valid analysis + one valid interpretation + one later failed interpretation (under `interpretation-failures/`), `export` picks the valid one.
31. **Export with `--interpretation-dir` override.** Explicit flag wins over latest-matching discovery.
32. **Export fails cleanly on missing analysis.** Empty XDG analysis dir → non-zero exit, message contains `no analysis runs found`.
33. **Export silently overwrites existing output file.** `-o report.ipynb` targeting a pre-existing file overwrites it without prompting. (See `todos/middens-export-overwrite-ux.md` for future refinement.)
34. **Notebook metadata contract.** The notebook's top-level `metadata.middens` object contains keys `analysis_run_id`, `analysis_run_path`, `middens_version`, and (when an interpretation was loaded) `interpretation_id`, `interpretation_path`.
35. **Notebook embeds pre-executed outputs.** Per-technique code cells that load the technique's headline table (first `TableRef` in `technique.tables`) have non-empty `outputs` arrays containing at least one `display_data` entry with both `text/html` and `text/plain` mime bundles; the first 10 rows of the headline table round-trip through the HTML bundle.
36. **Notebook is self-contained.** Opening `report.ipynb` in a viewer that cannot execute Python still renders all tables, findings, and conclusions from the embedded pre-executed outputs.

#### Integration

37. **End-to-end triad.** `analyze <fixture>` → `interpret` (with mocked runner) → `export` produces a notebook whose top cell names the analysis run ID, middle cells contain per-technique summaries + tables + interpretations, and the bottom cells expose exploratory starters.
38. **Idempotent re-export.** Running `export` twice in a row with the same analysis + interpretation produces byte-equal `.ipynb` files — all timestamps in the notebook are sourced from the analysis `created_at`, not generation time.

### 4.2 Definition of done

- [ ] All 38 acceptance scenarios pass under `cargo test`.
- [ ] `cargo build --release` succeeds with the chosen Parquet library.
- [ ] Release binary size increase documented in the PR description; `arrow2` fallback taken if polars adds >5MB.
- [ ] `middens analyze`, `middens interpret`, `middens export` all show up in `middens --help`.
- [ ] `middens --help` text for each command describes defaults and the XDG path.
- [ ] `docs/HANDOFF.md` updated: workstream 2 marked complete, current commit SHAs recorded, a worked example captured.
- [ ] `README.md` + `middens/README.md` reflect the triad command shape.
- [ ] No regression in the 270 existing Cucumber scenarios.
- [ ] Dry-run of `interpret` against a real analysis run produces a prompt that a human reviewer agrees "a model could answer this usefully" (manual step, not test-enforced).
- [ ] One live end-to-end run against a real corpus on at least one runner (`claude-code` preferred since it's what the user runs) — notebook opens in JupyterLab and is visually sensible.

## 5. Open questions

- **Parquet library choice.** Final decision belongs to Group A. Default recommendation: `polars`, fall back to `arrow2` if release-binary size jumps >5MB.
- **Response parser marker convention.** `<!-- technique: <slug> -->` is a guess. May need iteration once real LLM output lands in dry-run testing. Strictness rules (missing/duplicate/unknown slugs) are deferred to `todos/interpret-parser-strictness.md`.
- **Default-view format configurability.** `--default-view markdown` is the only value this milestone needs. Keep the flag but constrain to one value until more renderers land.

## 6. Review history

- **2026-04-09:** Initial draft reviewed by CodeRabbit (8 findings), Gemini 2.5 Pro (11 findings), Codex (8 findings). Amended in a single pass resolving all P1s and most P2s; deferred items filed as todos (`todos/middens-export-markdown-format.md`, `todos/middens-export-overwrite-ux.md`, `todos/interpret-parser-strictness.md`).
