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
        run-<uuidv7>/
            manifest.json
            data/
                <technique_slug>.parquet    # one file per technique, one table per technique
                ...
            sessions.parquet                # canonical sessions table
            default-view.md                 # ergonomic sidecar, regeneratable
    interpretation/
        <analysis-run-slug>/
            <runner-slug>-<uuidv7>/
                manifest.json               # points back at analysis run
                conclusions.md              # overall cross-technique narrative
                <technique_slug>-conclusions.md
                ...
                prompt.md                   # exact prompt sent to the runner
    interpretation-failures/
        <analysis-run-slug>/
            <runner-slug>-<uuidv7>/
                prompt.md                   # prompt that was sent
                raw-response.txt            # whatever the runner emitted
                error.txt                   # parse diagnostic or stderr
    interpretation-dryruns/
        <analysis-run-slug>/
            <runner-slug>-<uuidv7>/
                prompt.md                   # prompt that would have been sent
```

If `$XDG_DATA_HOME` is unset, fall back to `~/.local/share/` per the XDG base-directory spec.

### 2.2 Run addressing and slug format

- **Analysis run ID:** `run-<uuidv7>` where `<uuidv7>` is a canonical UUIDv7 string (RFC-9562, hyphenated form). UUIDv7 embeds a Unix-millisecond timestamp in its leading bits, so **lexicographic sort by directory name is equivalent to chronological sort by creation time**. No separate timestamp component is needed; there is no drift between "UUID time" and "directory name time" because they are the same value.
- **Interpretation slug:** `<runner-slug>-<uuidv7>` where `runner-slug ∈ {claude-code, codex, gemini, opencode}`. Within a single `<analysis-run-slug>` directory, lexicographic sort descending by slug produces the most-recent-first order, because UUIDv7 dominates the ordering after the runner-slug prefix. To find the most-recent interpretation across runners, the caller filters by runner first (or ignores the prefix and sorts by the UUID suffix alone).
- **Dry-run slug:** same format as the interpretation slug, but stored under `interpretation-dryruns/`. Dry runs are neither successes nor failures and must never be considered by discovery.
- **Corpus fingerprint:** SHA-256 of a newline-joined, lexicographically sorted list of parser-assigned session IDs from the corpus. First 8 hex chars become `corpus_fingerprint.short`, full hex becomes `corpus_fingerprint.manifest_hash`. The corpus fingerprint lives in the analysis manifest — it is **not** part of the run ID. This keeps run IDs independent of corpus identity and lets `analyze` on an empty or fingerprint-unstable corpus still succeed.
- **Reference back:** the interpretation manifest carries `analysis_run_id` and an absolute path to the analysis dir it interprets. Cross-run mixing is a user error: if `--interpretation-dir` points at an interpretation whose `analysis_run_id` differs from the currently-loaded analysis, `export` **still renders the notebook** — it does not validate the pairing, because the user may legitimately want to compare an old interpretation against a re-run analysis. This behaviour is documented loudly in `--help` and the README: *"passing a mismatched interpretation produces a coherent-looking but nonsensical notebook; you pointed it at that directory, you get to keep both pieces."*

### 2.3 Data model

```text
RECORD AnalysisManifest:
  run_id: String                         -- "run-0190e4b4-7e1c-7c4a-9f2b-5c9ab3f12de0"
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
  table: Option<TableRef>                -- at most one table per technique (v1 constraint)
  figures: List<FigureSpec>
  errors: List<String>                   -- per-technique errors; empty on success

RECORD TableRef:
  name: String                           -- "State Transitions"
  parquet: String                        -- "data/hsmm.parquet" — matches technique_slug
  row_count: Int
  column_types: Option<List<ColumnType>> -- from TechniqueResult if supplied

ENUM ColumnType: Int | Float | String | Bool | Timestamp

ENUM FigureKind:
  VegaLite(Value)                        -- JSON spec, embedded in manifest if <10KB
  TableRef { chart_type: ChartType }     -- implicitly references the technique's single table

ENUM ChartType: Line | Bar | Heatmap | Scatter | Histogram | Boxplot

RECORD InterpretationManifest:
  interpretation_id: String              -- "claude-code-0190e4b5-7e1c-7c4a-9f2b-5c9ab3f12de0"
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
    [--default-view FORMAT]              -- clap enum; v1 accepts {markdown} only.
                                         -- Any other value fails at parse time with the
                                         -- clap "invalid value for '--default-view'" error.
                                         -- The flag exists so future renderers can slot in
                                         -- without reshaping the CLI surface.

middens interpret
    [--analysis-dir DIR]                 -- default: latest valid run under XDG analysis/
    [--model RUNNER/MODEL-ID]            -- **MUST contain at least one '/'**.
                                         -- Runners: {claude-code, codex, gemini, opencode}.
                                         -- Model-id is free-form, passed verbatim to the
                                         -- runner. Parse: split on first '/' only; everything
                                         -- after is model-id (may contain further '/').
                                         -- Examples:
                                         --   claude-code/claude-opus-4-6
                                         --   codex/gpt-5.4-codex
                                         --   gemini/gemini-3.1-pro-preview
                                         --   opencode/kimi-for-coding/k2p5
                                         --   opencode/zai-coding-plan/glm-5.1
                                         -- Inputs without '/' (e.g. --model claude-code)
                                         -- FAIL at parse time with the expected form + an
                                         -- example for each runner. Never silently resolved
                                         -- to a runner-only default. See fail-fast rule in
                                         -- CLAUDE.md.
                                         -- When the flag is omitted entirely, interpret walks
                                         -- the runner fallback chain and invokes the first
                                         -- available runner with no explicit model flag.
    [--output-dir DIR]                   -- default: $XDG_DATA_HOME/com.../interpretation/<analysis-run-slug>/<interpretation-slug>/
    [--dry-run]                          -- write prompt to interpretation-dryruns/, skip runner call

middens export
    [--analysis-dir DIR]                 -- default: latest valid under XDG analysis/
    [--interpretation-dir DIR]           -- default: latest valid matching under interpretation/
                                         -- (never interpretation-failures/ or
                                         -- interpretation-dryruns/). Optional.
                                         -- NOTE: if the caller points this at an
                                         -- interpretation whose analysis_run_id differs from
                                         -- the loaded analysis, the resulting notebook is
                                         -- COHERENT-LOOKING BUT NONSENSICAL. The CLI does not
                                         -- validate the pairing. You pointed it at that
                                         -- directory; you get to keep both pieces.
                                         -- Documented in --help and README accordingly.
    [--no-interpretation]                -- explicitly skip interpretation even if present
    [--format FORMAT]                    -- clap enum; v1 accepts {jupyter} only.
                                         -- Any other value fails at parse time.
    [-o FILE]                            -- default: report.ipynb in cwd (overwritten silently)
```

**Notes on `--model` parsing:**

The split-on-first-`/` rule is deliberate so OpenCode's native `<provider>/<model>` format passes through untouched. `opencode/kimi-for-coding/k2p5` → runner=`opencode`, model-id=`kimi-for-coding/k2p5`. Each runner adapter decides how its model-id maps to the runner's own CLI syntax (some use `--model`, some use `-m`, OpenCode uses `--model <provider>/<model>` verbatim). When `--model` is omitted, the runner is invoked with no explicit model flag — each runner picks its own native default. When the user supplies an unknown runner prefix, `interpret` fails with a message listing supported runners and pointing at the `--help` examples.

### 2.5 Behavioural rules

**`analyze`:**

1. Runs the existing analysis pipeline (discover → parse → classify → techniques).
2. Captures a single `now()` value at the start of the run. Generates `run_id = "run-" + uuidv7_from_time(now)` so the UUID's embedded timestamp and the manifest `created_at` field share the exact same instant. Computes the corpus fingerprint and stores it in the manifest (not in the run ID).
3. Writes `manifest.json` + one Parquet file per technique under `data/` (one technique → one file → at most one table, per the v1 data model) + a top-level `sessions.parquet` with the canonical sessions table.
4. **PII writer-side check.** Before writing any Parquet file, the writer validates each `Table` against a tokenised column blocklist, a type-consistency check, and a value-length cap:
   - **Tokenisation:** split each column name on any non-alphanumeric character (`_`, `-`, `.`, digits, etc.), lowercase each token, treat the result as a set.
   - **Blocklisted tokens** (exact match against any token in the set): `path`, `paths`, `cwd`, `filename`, `filenames`, `filepath`, `body`, `prompt`, `raw`, `text`, `message`, `messages`, `content`, `source`, `snippet`, `excerpt`.
   - **Examples:** `raw_data` → tokens `{raw, data}` → `raw` matches → **blocked**. `total_messages` → tokens `{total, messages}` → `messages` matches → **blocked**. `context_length` → tokens `{context, length}` → no match → **passes**. `file_path` → tokens `{file, path}` → `path` matches → **blocked**. `n_turns` → tokens `{n, turns}` → no match → **passes**.
   - **`column_types` consistency check:** if the technique declared `column_types`, the writer validates that each in-memory column's actual type matches the declared type before serialisation. Mismatch → fail loudly with the column index, declared type, and actual type.
   - **Value-length cap:** no `String`-typed column value may exceed 200 characters.
   - **On any violation:** fail loudly, naming the offending technique, table, column, and (for value-cap violations) the row index of the first offending cell. Refuse to write the run. No partial output on disk.
   - **Overblock is acceptable.** If a legitimate column trips the blocklist (e.g., `total_messages` above is a count, not PII), the technique author renames the column (`msg_count` works). Error messages explicitly suggest this. Rationale: false positives are cheap to fix; false negatives leak PII.
   - This is a writer-side invariant. Techniques are expected to produce derived numerics, not raw session content — the check exists to catch mistakes, not to sanitise real PII.
5. Writes `default-view.md` unless `--no-default-view` is set. Default view is produced via the same `ViewRenderer` path that `export` uses — no shortcut from in-memory results to markdown.
6. On technique error: write the error into `TechniqueEntry.errors` and continue. Non-zero exit only if zero techniques succeeded.
7. Prints the run-id and storage path to stdout on success.
8. **`--split` stratification under the storage layer.** When `--split` is set, the pipeline partitions discovered sessions into the `interactive` and `subagent` strata (existing behaviour, preserved) and runs the full technique battery on each stratum independently. The storage layout becomes:

    ```text
    $XDG_DATA_HOME/com.lightless-labs.third-thoughts/analysis/run-<uuidv7>/
        manifest.json                  # top-level — carries run_id, corpus fingerprint,
                                       #   analyzer fingerprint, and a `strata` field
                                       #   listing {name, session_count, manifest_ref}
                                       #   for each stratum.
        interactive/
            manifest.json              # stratum manifest — same schema as the non-split
                                       #   manifest, but `run_id` is inherited from the
                                       #   top-level and the stratum manifest adds a
                                       #   `stratum: "interactive"` field.
            data/
                <technique_slug>.parquet
                ...
            sessions.parquet           # only interactive sessions
            default-view.md
        subagent/
            manifest.json              # `stratum: "subagent"`
            data/
                <technique_slug>.parquet
                ...
            sessions.parquet           # only subagent sessions
            default-view.md
    ```

    Rationale for the nested layout (rather than two separate top-level run dirs): `--split` is logically one analysis of one corpus, not two separate runs. Sharing a single `run_id` lets `export` render a single notebook with both strata side-by-side (future work), and keeps `interpret` addressable by run ID the same way the non-split case is.

    When `--split` is **not** set, there is no top-level `strata` field and no `interactive/` / `subagent/` subdirs — the layout is exactly as described in §2.1.

    `interpret` and `export` default-path resolution for a split run: if `--analysis-dir` points at the top-level `run-<uuidv7>/` dir, those commands treat it as a split run and operate over both strata. If the caller points at `<run>/interactive/` or `<run>/subagent/`, they operate over that single stratum only. This is the only place `interpret` / `export` accept a sub-directory of a run; in all other cases `--analysis-dir` points at the `run-<uuidv7>/` root.

**`interpret`:**

1. Resolves `--analysis-dir` (or discovers the most-recently-named *valid* run under the XDG analysis root — valid = contains a parseable `manifest.json`; sort by directory name descending, which is chronological by UUIDv7 construction).
2. Parses `--model`: the string **must** contain at least one `/`. The prefix before the first `/` is the runner slug; everything after is the model-id, passed verbatim to the runner. If the string has no `/`, `interpret` exits non-zero at parse time with a message showing the expected form and four concrete examples (one per runner). No best-guess resolution to a runner-only mode — see the fail-fast rule in `CLAUDE.md`.
3. If `--model` is omitted, walks the fallback chain (`claude-code` → `codex` → `gemini` → `opencode`), picking the first whose binary is on `PATH` (`which`-based), and invokes it with no explicit model flag (the runner picks its own default).
4. If the chosen runner is missing from `PATH`: fail with a clear message listing which runners were tried.
5. Captures a single `now()` value at the start of the run. Allocates an interpretation slug `<runner-slug>-<uuidv7_from_time(now)>` and a **temp sibling directory** at the common parent of all three possible final destinations: `$XDG_DATA_HOME/com.lightless-labs.third-thoughts/.tmp-<uuidv7>/`. The common-parent placement guarantees that the final `rename` call stays on the same filesystem regardless of which destination is chosen (`interpretation/`, `interpretation-failures/`, or `interpretation-dryruns/`), so the rename is atomic on every POSIX filesystem.
6. Builds the prompt from an embedded template, substituting manifest + per-technique summaries + scalar findings + **headline table excerpts**. Writes the prompt to `<tmp>/prompt.md` before any runner call.
   - **Headline table = the `TechniqueEntry.table` value** (one table per technique in v1). If the technique declares no table, it contributes no excerpt. Each excerpt is the first **10** rows of that table, serialised as markdown.
7. Calls the runner as a subprocess. Each runner has an adapter that knows its CLI shape:
   - `claude-code` → `claude -p "$(cat prompt.md)"` (+ `--model <model-id>` if set)
   - `codex` → `codex exec --skip-git-repo-check --full-auto -o <tmp>/response.md "$(cat prompt.md)"` (+ `--model <model-id>` if set)
   - `gemini` → `gemini -y -s false --prompt "$(cat prompt.md)"` (+ `-m <model-id>` if set)
   - `opencode` → `opencode run --format json --model <model-id> "$(cat prompt.md)"` (opencode has no native default model — the runner adapter refuses to invoke opencode without an explicit `model_id`, failing at adapter time rather than letting opencode emit its own error)
8. Parses the runner's response into: one overall `conclusions.md` + one `<technique_slug>-conclusions.md` per technique. The prompt instructs the model to emit section markers `<!-- technique: <slug> -->`. The parser splits on those markers; content before the first marker becomes the overall `conclusions.md`. **Leading-marker edge case:** if the response begins immediately with a technique marker (no pre-marker content), `conclusions.md` is written as an empty file, not omitted — downstream readers (`export` and renderers) never have to special-case a missing `conclusions.md`.
9. Writes `manifest.json` into the temp dir, then **atomically renames** the temp dir to its success destination `<output-root>/interpretation/<analysis-run-slug>/<interpretation-slug>/`. Because the destination name contains a fresh UUIDv7, there is no possibility of collision — there is no `--force` flag.
10. **On any failure** (runner non-zero exit, empty output, unparseable sections, opencode without `--model`, unknown runner prefix, etc.): write `error.txt` and `raw-response.txt` (if any response was captured) **into the temp dir `.tmp-<uuidv7>/`** *before* calling rename, then atomically rename the temp dir to `<output-root>/interpretation-failures/<analysis-run-slug>/<interpretation-slug>/`, exit non-zero. Writing the diagnostic artifacts before the rename guarantees that a crash mid-write leaves *either* a clean temp dir (to be cleaned up on next run) *or* a complete failure dir — never a half-written failure dir. The runner's own stderr is surfaced to the user's terminal; installed-but-unauthenticated runners surface whatever the runner emits, which is considered a correct outcome (the user owns the runner's stderr).
11. `--dry-run`: writes `prompt.md` into the temp dir, then atomically renames the temp dir to `<output-root>/interpretation-dryruns/<analysis-run-slug>/<interpretation-slug>/`. Skips runner call, exits 0 with the dry-run dir path printed to stdout. Dry runs are neither successes nor failures and must never be picked up by `export` discovery.

**`export`:**

1. Resolves `--analysis-dir` (default: latest *valid* under the XDG analysis root).
2. Resolves `--interpretation-dir` (default: latest *valid* matching interpretation under `interpretation/<analysis-run-slug>/`; `--no-interpretation` forces skip). "Valid" = contains a parseable `manifest.json`. Failed interpretations under `interpretation-failures/` are never considered.
3. Loads analysis via `AnalysisRun` reader; loads interpretation if present.
4. Renders a notebook via the `IpynbRenderer` impl of `ViewRenderer`.
5. Writes the output file (default: `report.ipynb` in cwd, **silently overwriting** if it exists).
6. **Must succeed with analysis alone, no interpretation.** Tested as a first-class path.

**Default-path resolution:**

- "Latest valid" = scan the relevant XDG dir (`analysis/` for analysis runs, `interpretation/<analysis-run-slug>/` for interpretations — never `interpretation-failures/`, never `interpretation-dryruns/`), keep only subdirectories matching the slug regex AND containing a parseable `manifest.json`, sort the survivors by directory name descending, return the first. UUIDv7 embeds a millisecond-resolution Unix timestamp in its leading bits, so lexicographic-descending sort on the UUID portion is equivalent to most-recent-first. **No `mtime` is ever consulted** — that would reintroduce exactly the ambiguity this design is trying to avoid.
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

1. **Round-trip a minimal analysis.** Given a fixture corpus with 2 sessions, when `analyze` runs, then `manifest.json` and at least one `data/*.parquet` file exist, the manifest validates against the schema, and `AnalysisRun::load` reads them back and returns a structure where technique count, per-technique row counts, and scalar findings match what the pipeline computed in memory.
2. **Corpus fingerprint is stable.** Running `analyze` twice against the same corpus produces the same `corpus_fingerprint.manifest_hash` and the same `corpus_fingerprint.short`; only the `run_id` (different UUIDv7 per invocation) differs between runs.
3. **One table per technique, round-trips through Parquet.** A single-table technique writes to `data/<technique_slug>.parquet`, and `AnalysisRun::load` reads it back such that the loaded `TechniqueEntry.table` has the same row count, column count, column types, and first-row values as the in-memory state. (The "only one table per technique" rule is enforced by the type system — `TechniqueEntry.table: Option<TableRef>` — so there is nothing to *test* for multi-table rejection; the compiler rejects it. This scenario covers only the happy-path round-trip.)
4. **Type-homogeneous columns survive round-trip.** A technique that declares `column_types: [Int, Float, String]` produces a Parquet file whose schema matches, and loading it back preserves the types.
5. **`column_types` mismatch is rejected.** A technique that declares `column_types: [Int]` but supplies a `Float` column at position 0 causes `analyze` to fail loudly, naming the column index, the declared type, and the actual type. No partial output.
6. **PII tokenised column-name blocklist — blocked cases.** A test technique declaring a column named `raw_data` (or `total_messages`, or `file_path`) causes `analyze` to fail, naming the offending technique + column + matched blocklist token, suggesting a rename, and leaving no partial run directory on disk.
7. **PII tokenised column-name blocklist — permitted cases.** A test technique declaring columns named `context_length`, `n_turns`, and `msg_count` passes the PII check and the run succeeds.
8. **PII value-length cap.** A test technique that emits a `String` column whose values exceed 200 characters causes `analyze` to fail with an error naming the technique, column, and the row index of the first offending cell. No partial output.

#### Analyze

9. **Analyze writes the expected layout.** `middens analyze <fixture>` produces `<run-dir>/manifest.json`, `<run-dir>/sessions.parquet`, `<run-dir>/data/*.parquet`, `<run-dir>/default-view.md`.
10. **Run ID format.** The run dir matches `^run-[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (canonical UUIDv7, no date prefix).
11. **UUIDv7 timestamp matches manifest `created_at`.** The Unix millisecond timestamp embedded in the leading 48 bits of the UUIDv7 in `run_id` equals the Unix millisecond timestamp of `manifest.json`'s `created_at` field. Both are derived from a single `now()` capture at run start.
12. **Multiple runs back-to-back.** Running `analyze` twice back-to-back (within the same millisecond if possible) produces two distinct run dirs. UUIDv7's random tail guarantees uniqueness; lexicographic sort descending on the run-dir names returns the more recent run first.
13. **`--no-default-view` suppresses default view.** When set, `default-view.md` does not exist in the run dir.
14. **Default view is produced via the ViewRenderer path.** The `analyze`-emitted `default-view.md` is byte-equal to what `MarkdownRenderer::render(&AnalysisRun::load(<run>))` returns when invoked directly in a test. (Renderer-level byte-equality test; markdown export from the `export` command is deferred — see `todos/middens-export-markdown-format.md`.)
15. **`--default-view invalid-format` fails at parse time.** Running `analyze --default-view json` (or any non-`markdown` value) exits non-zero with clap's usual "invalid value for '--default-view'" error, no partial output written.
16. **Technique errors do not abort the run.** With a fixture that causes one technique to fail, `manifest.json` still exists, the failing technique's `errors` field is non-empty, and at least one other technique's output is present.
17. **Analyze default output dir is XDG.** With no `--output-dir`, runs land under `$XDG_DATA_HOME/com.lightless-labs.third-thoughts/analysis/`.
18. **`--split` writes nested stratum subdirs.** `middens analyze --split <mixed-corpus>` produces a single `run-<uuidv7>/` dir containing `manifest.json` (top-level with `strata` field), `interactive/{manifest.json,data/,sessions.parquet,default-view.md}`, and `subagent/{manifest.json,data/,sessions.parquet,default-view.md}`. There is no `data/` at the top level and no top-level `sessions.parquet`.
19. **`--split` top-level manifest references strata.** The top-level `manifest.json` carries a `strata` field that is a list of `{name, session_count, manifest_ref}` entries, with `manifest_ref` pointing at the per-stratum `manifest.json` by relative path.
20. **`--split` stratum manifests carry stratum name.** Each per-stratum `manifest.json` contains `stratum: "interactive"` (or `"subagent"`) and inherits the same `run_id` as the top-level.
21. **Without `--split`, no stratum subdirs.** `middens analyze <mixed-corpus>` (no `--split`) produces a flat layout with `data/` and `sessions.parquet` at the top level, no `interactive/` or `subagent/` subdirs, and no `strata` field in the manifest.

#### Interpret

22. **Default analysis discovery by name sort.** With two valid runs under the XDG analysis dir, `interpret` with no `--analysis-dir` picks the one whose directory name sorts descending first (equivalently, the one with the higher UUIDv7). Discovery does **not** consult `mtime` — a test that `touch`es the older run's directory does not change the selection.
23. **Invalid analysis runs are skipped during discovery.** With two runs present where the lexicographically-greater one has a corrupt/missing `manifest.json`, `interpret` picks the lexicographically-lesser valid one instead.
24. **No analysis runs → clear error.** With an empty XDG analysis dir, `interpret` exits non-zero with a message containing `no analysis runs found`.
25. **Runner fallback picks first available.** With mocked `which` resolving `claude-code` only, `interpret` selects `claude-code`. With only `gemini` available, it selects `gemini`. With none of `{claude-code, codex, gemini, opencode}` available, it fails with a message listing all four.
26. **Explicit `--model` overrides fallback with runner prefix.** `--model codex/gpt-5.4-codex` with `codex` absent from `PATH` fails cleanly with a message naming `codex`.
27. **`--model` parses on first `/` only.** `--model opencode/kimi-for-coding/k2p5` resolves to runner=`opencode`, model-id=`kimi-for-coding/k2p5` (the second `/` is preserved). Captured in the interpretation manifest as `runner: "opencode"`, `model_id: "kimi-for-coding/k2p5"`.
28. **`--model` without a slash fails at parse time.** `--model claude-code` (no `/`) exits non-zero with a message showing the expected `<runner>/<model-id>` form and at least four concrete examples (one per runner). No runner auto-resolution, no best-guess.
29. **Unknown runner prefix fails with helpful error.** `--model foo/bar` exits non-zero with a message listing the four supported runner slugs.
30. **Dry-run writes prompt, skips runner, lands in interpretation-dryruns/.** `--dry-run` produces a `prompt.md` under `interpretation-dryruns/<analysis-run-slug>/<interpretation-slug>/`, prints its path to stdout, does not invoke any subprocess, and exits 0. The dry-run dir never appears under `interpretation/` or `interpretation-failures/`.
31. **Interpretation output layout on success.** The interpretation dir contains `manifest.json`, `prompt.md`, `conclusions.md`, and one `<technique_slug>-conclusions.md` per technique present in the analysis.
32. **Empty `conclusions.md` on leading marker.** With a mocked runner emitting a response that starts immediately with `<!-- technique: <slug> -->` (no pre-marker content), the successful interpretation dir still contains a `conclusions.md` file — empty, zero bytes. Not omitted.
33. **Interpretation manifest references analysis.** The interpretation `manifest.json` carries `analysis_run_id` and `analysis_run_path` matching the analysis it interpreted, plus `runner` and `model_id`.
34. **Response parsing failure moves artifacts to failures dir.** With a mocked runner emitting output without section markers, `interpret` fails non-zero, the temp dir is renamed to `interpretation-failures/<analysis-run-slug>/<slug>/` containing `prompt.md` + `raw-response.txt` + `error.txt`, all three of which were written *before* the final rename call, and no directory appears under `interpretation/<analysis-run-slug>/`.
35. **Atomic write on success.** During a successful `interpret`, no directory exists at the final destination path until after the temp dir is fully written and `manifest.json` is serialised. (Test: inspect filesystem state mid-run via a pause hook.)
36. **Interpretation slug format.** The interpretation subdir matches `^(claude-code|codex|gemini|opencode)-[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`.
37. **OpenCode without `--model` is an error.** Running `interpret` with runner auto-detected to `opencode` (the only runner on PATH) but without `--model` fails with `opencode requires an explicit --model` because opencode's CLI has no native default.

#### Export

38. **Export with interpretation.** Given an analysis + an interpretation, `export --format jupyter -o report.ipynb` produces a file that validates as nbformat v4, contains a top-level conclusions cell with text from the overall `conclusions.md`, and contains per-technique cells each including the corresponding `<slug>-conclusions.md` text.
39. **Export without interpretation.** With `--no-interpretation` (or no interpretation present), the notebook still renders with all technique sections but no conclusions cells. Exit 0.
40. **Export default-path discovery.** With no flags, `export` resolves to the latest valid analysis and latest valid matching interpretation automatically via name-sort descending (no `mtime`). The produced notebook's `metadata.middens` object contains `analysis_run_id` + `analysis_run_path` matching the analysis, and `interpretation_id` + `interpretation_path` matching the interpretation.
41. **Export ignores failed and dry-run interpretations.** With a valid analysis + one valid interpretation + one later failed interpretation (under `interpretation-failures/`) + one later dry-run (under `interpretation-dryruns/`), `export` picks the valid one — both non-success locations are invisible to discovery.
42. **Export with `--interpretation-dir` override.** Explicit flag wins over default discovery.
43. **Export does not validate cross-run pairing.** Given an analysis `A1` and an interpretation `I2` whose manifest's `analysis_run_id` references a different analysis `A2`, `export --analysis-dir A1 --interpretation-dir I2` succeeds, produces a notebook with analysis `A1`'s data and `I2`'s narrative, and does not warn or fail. The `--help` text for `--interpretation-dir` documents this as a caller-beware behaviour.
44. **Export fails cleanly on missing analysis.** Empty XDG analysis dir → non-zero exit, message contains `no analysis runs found`.
45. **Export silently overwrites existing output file.** `-o report.ipynb` targeting a pre-existing file overwrites it without prompting. (See `todos/middens-export-overwrite-ux.md` for future refinement.)
46. **Export rejects invalid `--format` values at parse time.** `export --format html` (or any non-`jupyter` value) exits non-zero with clap's usual "invalid value for '--format'" error, no partial output written.
47. **Notebook metadata contract.** The notebook's top-level `metadata.middens` object contains keys `analysis_run_id`, `analysis_run_path`, `middens_version`, and (when an interpretation was loaded) `interpretation_id`, `interpretation_path`.
48. **Notebook embeds pre-executed outputs.** Per-technique code cells that load the technique's single table (`technique.table`) have non-empty `outputs` arrays containing at least one `display_data` entry with both `text/html` and `text/plain` mime bundles; the first 10 rows of that table round-trip through the HTML bundle.
49. **Notebook is self-contained.** Opening `report.ipynb` in a viewer that cannot execute Python still renders all tables, findings, and conclusions from the embedded pre-executed outputs.

#### Integration

50. **End-to-end triad.** `analyze <fixture>` → `interpret` (with mocked runner) → `export` produces a notebook whose top cell names the analysis run ID, middle cells contain per-technique summaries + tables + interpretations, and the bottom cells expose exploratory starters.
51. **Idempotent re-export.** Running `export` twice in a row with the same analysis + interpretation produces byte-equal `.ipynb` files — all timestamps in the notebook are sourced from the analysis `created_at`, not generation time.

### 4.2 Definition of done

- [ ] All 51 acceptance scenarios pass under `cargo test`.
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

- **2026-04-09 (pass 1):** Initial draft reviewed by CodeRabbit (8 findings), Gemini 2.5 Pro (11 findings), Codex (8 findings). Amended in a single pass resolving all P1s and most P2s; deferred items filed as todos (`todos/middens-export-markdown-format.md`, `todos/middens-export-overwrite-ux.md`, `todos/interpret-parser-strictness.md`).
- **2026-04-09 (pass 2):** Amended spec re-reviewed by CodeRabbit (2 findings, both fixed on the spot) and Gemini 3.1 Pro (11 new findings). Second amendment: dropped date prefix from run/interpretation slugs (UUIDv7 alone handles ordering and uniqueness), collapsed `TechniqueEntry.tables: List<TableRef>` → `table: Option<TableRef>` (one-table-per-technique as a v1 constraint), reworked PII blocklist as tokenised exact-match to avoid substring false positives, made `--model` without `/` fail at parse time (see new fail-fast convention in parent CLAUDE.md), added `--default-view` and `--format` as clap enums rejecting unknown values, introduced `interpretation-dryruns/` as a third sibling location so dry runs are neither successes nor failures, moved failure diagnostic writes (`error.txt` + `raw-response.txt`) inside the temp dir before the rename to preserve atomicity, and synchronised the UUIDv7 timestamp with manifest `created_at` via a single `now()` capture. Scenario count 38 → 47.
- **2026-04-09 (pass 3):** Third-pass Codex review got stuck on its `adversarial-document-reviewer` skill auto-activation and had to be killed, but two real findings were extracted from the partial JSONL stream: (1) the existing `split.feature` exercises `middens analyze --split` but the spec never said how `--split` interacts with the new storage layer, and (2) scenario 3's "fails at the type level" phrasing is untestable as a Cucumber feature without a `trybuild` compile-fail harness. Third amendment: added full `--split` storage contract (nested `interactive/` + `subagent/` stratum subdirs sharing one top-level `run_id`, with a `strata` field on the top-level manifest and `stratum` field on each per-stratum manifest), four new acceptance scenarios for `--split`, and rewrote scenario 3 as a pure happy-path round-trip with a parenthetical noting that the one-table rule is enforced by the compiler and has nothing to test. Scenario count 47 → 51.
