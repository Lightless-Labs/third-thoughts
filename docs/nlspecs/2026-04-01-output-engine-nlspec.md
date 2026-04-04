---
date: 2026-04-01
topic: middens-output-engine
source_spec: docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md
status: draft
---

# Middens Output Engine

## 1. Why

### 1.1 Problem Statement

The middens CLI can parse session logs, classify them, and run 5 analytical techniques — but has no way to present results. The `TechniqueResult` struct contains findings, data tables, and figure specifications, but all three output modules (`markdown.rs`, `json.rs`, `ascii.rs`) are empty stubs. Without an output engine, `middens analyze` cannot produce usable artifacts.

### 1.2 Design Principles

- **TechniqueResult is the only input.** The output engine knows nothing about specific techniques. It renders whatever a `TechniqueResult` contains. This keeps techniques and output decoupled.
- **Each format is independently useful.** Markdown reports are human-readable. JSON is machine-consumable. ASCII sparklines are for terminal glancing. A user may want any combination.
- **Deterministic output.** Same `TechniqueResult` → same output bytes. No timestamps, random IDs, or environment-dependent content in the output (except the YAML frontmatter `generated_at` field, which is passed in, not computed).
- **No external dependencies for core formats.** Markdown and JSON use only `std` + `serde_json`. ASCII uses no crates. Parquet and Vega-Lite are deferred to a future phase.

### 1.3 Layering and Scope

The output engine covers three renderers:
- **Markdown**: YAML-frontmatter report per technique
- **JSON**: Raw data export per technique
- **ASCII**: Sparkline and mini-chart primitives for embedding in markdown or terminal output

Out of scope for this NLSpec: Parquet export, Vega-Lite figure rendering, cross-technique synthesis reports, results directory management.

## 2. What

### 2.1 Data Model

```text
-- Input (already exists in techniques/mod.rs)
RECORD TechniqueResult:
  name: String
  summary: String
  findings: Vec<Finding>
  tables: Vec<DataTable>
  figures: Vec<FigureSpec>

RECORD Finding:
  label: String
  value: JsonValue
  description: Option<String>

RECORD DataTable:
  name: String
  columns: Vec<String>
  rows: Vec<Vec<JsonValue>>

RECORD FigureSpec:
  title: String
  spec: JsonValue

-- Output metadata (new)
RECORD OutputMetadata:
  technique_name: String
  corpus_size: u64          -- number of sessions analyzed
  generated_at: String      -- ISO-8601 timestamp
  middens_version: String   -- from Cargo.toml
  parameters: Map<String, String>  -- technique-specific params passed in
```

### 2.2 Architecture

Three independent renderer functions. No shared state. No trait — plain functions taking `TechniqueResult` + `OutputMetadata` and returning `String` (for markdown/ASCII) or `serde_json::Value` (for JSON).

```text
render_markdown(result: &TechniqueResult, meta: &OutputMetadata) -> String
render_json(result: &TechniqueResult, meta: &OutputMetadata) -> Value
render_ascii_sparkline(values: &[f64], width: usize) -> String
render_ascii_bar(label: &str, value: f64, max: f64, width: usize) -> String
render_ascii_table(table: &DataTable, max_col_width: usize) -> String
```

### 2.3 Vocabulary

- **Frontmatter**: YAML metadata block delimited by `---` at the top of a markdown file
- **Sparkline**: A single-line visual representation of a data series using Unicode block characters (▁▂▃▄▅▆▇█)
- **Finding**: A labeled key-value result from a technique (e.g., `mean_entropy: 2.34`)
- **DataTable**: A named table of rows and columns, like a CSV with a name

## 3. How

### 3.1 Markdown Renderer

```text
FUNCTION render_markdown(result: &TechniqueResult, meta: &OutputMetadata) -> String:
  -- Step 1: YAML frontmatter
  output = "---\n"
  output += "technique: " + meta.technique_name + "\n"
  output += "corpus_size: " + str(meta.corpus_size) + "\n"
  output += "generated_at: " + meta.generated_at + "\n"
  output += "middens_version: " + meta.middens_version + "\n"
  IF meta.parameters is not empty:
    output += "parameters:\n"
    FOR key, value IN meta.parameters:
      output += "  " + key + ": " + value + "\n"
  output += "---\n\n"

  -- Step 2: Title and summary
  output += "# " + result.name + "\n\n"
  IF result.summary is not empty:
    output += result.summary + "\n\n"

  -- Step 3: Findings section
  IF result.findings is not empty:
    output += "## Findings\n\n"
    output += "| Finding | Value | Description |\n"
    output += "|---------|-------|-------------|\n"
    FOR finding IN result.findings:
      desc = finding.description OR ""
      output += "| " + finding.label + " | " + format_value(finding.value) + " | " + desc + " |\n"
    output += "\n"

  -- Step 4: Data tables
  FOR table IN result.tables:
    output += "## " + table.name + "\n\n"
    output += render_markdown_table(table)
    output += "\n"

  -- Step 5: Figures (as JSON code blocks for now)
  FOR figure IN result.figures:
    output += "## " + figure.title + "\n\n"
    output += "```json\n"
    output += pretty_print_json(figure.spec) + "\n"
    output += "```\n\n"

  RETURN output

FUNCTION render_markdown_table(table: &DataTable) -> String:
  -- Render as a standard markdown pipe table
  -- Column headers from table.columns
  -- Each row formatted with | separators
  -- Values formatted via format_value()
  -- Cap at 50 rows; if more, show first 25 + "..." + last 5

FUNCTION format_value(value: JsonValue) -> String:
  -- null -> "—"
  -- bool -> "yes" / "no"
  -- number (integer) -> formatted with no decimals
  -- number (float) -> 4 decimal places
  -- string -> as-is
  -- array/object -> compact JSON
```

### 3.2 JSON Renderer

```text
FUNCTION render_json(result: &TechniqueResult, meta: &OutputMetadata) -> Value:
  -- Wrap the TechniqueResult with metadata
  RETURN json!({
    "metadata": {
      "technique": meta.technique_name,
      "corpus_size": meta.corpus_size,
      "generated_at": meta.generated_at,
      "middens_version": meta.middens_version,
      "parameters": meta.parameters
    },
    "name": result.name,
    "summary": result.summary,
    "findings": result.findings,   -- serialize directly
    "tables": result.tables,       -- serialize directly
    "figures": result.figures      -- serialize directly
  })
```

### 3.3 ASCII Renderers

```text
FUNCTION render_ascii_sparkline(values: &[f64], width: usize) -> String:
  -- Map values to Unicode block characters ▁▂▃▄▅▆▇█
  -- 8 levels, linearly scaled between min and max of values
  -- If values.len() > width, downsample by averaging bins
  -- If values.len() <= width, use one char per value
  -- Empty input -> empty string
  -- All-equal values -> all ▄ (mid-level)

FUNCTION render_ascii_bar(label: &str, value: f64, max: f64, width: usize) -> String:
  -- Render: "label  ████████░░░░  0.75"
  -- Filled portion = (value / max) * width, using █ chars
  -- Unfilled portion = remaining width, using ░ chars
  -- Label left-padded to 20 chars
  -- Value right-aligned with 4 decimal places
  -- max == 0 -> empty bar

FUNCTION render_ascii_table(table: &DataTable, max_col_width: usize) -> String:
  -- Render a DataTable as a terminal-friendly ASCII table
  -- Column widths: min(max_col_width, max(header_len, max_value_len))
  -- Header row with column names
  -- Separator row with dashes
  -- Data rows with values truncated to max_col_width
  -- Cap at 30 rows; if more, show first 20 + "... (N more rows)" + last 5
```

## 4. Out of Scope

- **Parquet export**: Requires `polars` or `arrow2` crate. Deferred to Phase 3b.
- **Vega-Lite rendering**: `FigureSpec` is passed through as JSON in markdown code blocks. No rendering to SVG/PNG.
- **Cross-technique synthesis report**: The `middens report` command that aggregates multiple technique results. Separate NLSpec.
- **Results directory management**: Creating `results/{timestamp}/` directory structure, writing files to disk. The output engine produces strings/values — the caller decides where to write them.
- **Streaming/incremental output**: All renderers take a complete `TechniqueResult` and return a complete output.

## 5. Design Decision Rationale

**Why plain functions instead of a trait?** Three renderers with different return types (`String`, `Value`, `String`) don't share a meaningful interface. A trait would require a type parameter or enum return, adding abstraction without value. Plain functions are simpler and more discoverable.

**Why cap table rows at 50/30?** Large corpora produce tables with thousands of rows. Markdown tables with 5,000 rows are unreadable. The cap balances completeness (show first + last) with usability. JSON has no cap — it's the machine-readable format for full data.

**Why Unicode block characters for sparklines?** They render correctly in all modern terminals and markdown renderers. No external font or rendering dependency. Eight levels (▁-█) provide sufficient visual resolution for trends.

**Why `format_value` uses 4 decimal places?** Matches the precision used in technique findings (markov transition probabilities, entropy values, diversity indices). More decimals add noise; fewer lose meaningful precision.

## 6. Definition of Done

### 6.1 Markdown Renderer (mirrors 3.1)
- [ ] Produces valid YAML frontmatter with technique name, corpus_size, generated_at, middens_version
- [ ] Frontmatter includes parameters map when non-empty, omits when empty
- [ ] Title is `# technique_name`
- [ ] Summary rendered as paragraph after title; omitted when empty
- [ ] Findings rendered as a markdown pipe table with Finding, Value, Description columns
- [ ] Findings table omitted when no findings exist
- [ ] `format_value`: null → "—", bool → "yes"/"no", integer → no decimals, float → 4 decimals, string → as-is, array/object → compact JSON
- [ ] Each DataTable rendered as a markdown section with `## table_name` header
- [ ] DataTable rows capped at 50 (first 25 + "..." + last 5 when exceeded)
- [ ] FigureSpecs rendered as `## title` with JSON code block containing the spec
- [ ] Empty TechniqueResult (no findings, no tables, no figures) produces valid markdown with just frontmatter + title

### 6.2 JSON Renderer (mirrors 3.2)
- [ ] Output is a valid JSON object with `metadata` and result fields
- [ ] Metadata contains technique, corpus_size, generated_at, middens_version, parameters
- [ ] Findings, tables, and figures are serialized directly from TechniqueResult
- [ ] Empty TechniqueResult produces valid JSON with empty arrays

### 6.3 ASCII Renderers (mirrors 3.3)
- [ ] Sparkline maps values to 8 Unicode block levels (▁▂▃▄▅▆▇█) scaled between min and max
- [ ] Sparkline downsamples when values.len() > width
- [ ] Sparkline returns empty string for empty input
- [ ] Sparkline renders all-equal values as mid-level blocks
- [ ] Bar chart renders `label  ████░░  value` format with configurable width
- [ ] Bar chart handles max == 0 (empty bar, value shown as 0)
- [ ] Bar chart handles value > max (clamp to full bar)
- [ ] ASCII table renders column-aligned output with header, separator, and data rows
- [ ] ASCII table truncates values to max_col_width
- [ ] ASCII table caps at 30 rows (first 20 + summary + last 5 when exceeded)

### 6.4 Integration
- [ ] `render_markdown` output parses as valid YAML frontmatter + valid markdown
- [ ] `render_json` output parses as valid JSON and round-trips through serde
- [ ] All renderers handle a real `TechniqueResult` from the markov technique (integration smoke test)
