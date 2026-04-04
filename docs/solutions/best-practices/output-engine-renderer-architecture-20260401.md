---
title: "Output engine renderer architecture — functions over traits for heterogeneous return types"
date: 2026-04-01
category: best-practices
module: middens-output
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "Designing a multi-format output engine"
  - "Deciding between trait-based and function-based renderer architecture"
tags: [output-engine, renderer, architecture, rust, markdown, json, ascii]
---

# Output Engine Renderer Architecture — Functions Over Traits for Heterogeneous Return Types

## Context

Phase 3 of middens needed markdown, JSON, and ASCII renderers consuming the same `TechniqueResult` input but producing different output types (`String`, `serde_json::Value`, `String`). The natural Rust instinct is to define a `Renderer` trait, but the heterogeneous return types make a trait-based approach awkward without type parameters or enum wrappers that add complexity for no real benefit.

## Guidance

### 1. Plain functions over traits when return types differ

Each renderer is a standalone function:

```rust
pub fn render_markdown(result: &TechniqueResult, meta: &OutputMetadata) -> String;
pub fn render_json(result: &TechniqueResult, meta: &OutputMetadata) -> serde_json::Value;
pub fn render_ascii_table(table: &DataTable, max_col_width: usize) -> String;
pub fn render_ascii_sparkline(values: &[f64], width: usize) -> String;
pub fn render_ascii_bar(label: &str, value: f64, max: f64, width: usize) -> String;
```

A trait like `trait Renderer { type Output; fn render(...) -> Self::Output; }` would require callers to know the concrete type at the call site anyway, negating the polymorphism benefit. And a `trait Renderer { fn render(...) -> RendererOutput; }` with an enum wrapper just moves the type dispatch to runtime for no gain. Functions are simpler, more explicit, and fully type-safe.

### 2. `TechniqueResult` as universal input contract

All renderers accept `&TechniqueResult` as their primary input. Renderers know nothing about specific techniques — they operate on the generic structure of findings, tables, and figures. This means adding a new technique requires zero renderer changes, and adding a new renderer requires zero technique changes.

### 3. `OutputMetadata` struct for context

Context that is external to the technique result (technique name, corpus size, timestamp, version, parameters) is passed in via a dedicated struct rather than computed by renderers:

```rust
pub struct OutputMetadata {
    pub technique_name: String,
    pub corpus_size: u64,
    pub generated_at: String,
    pub middens_version: String,
    pub parameters: BTreeMap<String, String>,
}
```

This keeps renderers pure (deterministic) and testable. The caller constructs `OutputMetadata` once and passes it to whichever renderer is selected.

### 4. `format_value()` as the JSON-to-display bridge

A single `format_value()` function handles all JSON value types for human-readable display. This function is shared between markdown and ASCII renderers:

| JSON type | Display |
|-----------|---------|
| `null` | `—` (em dash) |
| `bool(true)` | `yes` |
| `bool(false)` | `no` |
| integer | no decimals (e.g., `42`) |
| float | 4 decimal places (e.g., `0.8550`) |
| float with `.0` fractional part | no decimals (e.g., `100`) |
| string | as-is |
| array/object | compact JSON |

This ensures consistent formatting across all human-readable outputs. The JSON renderer does not use `format_value()` — it preserves native JSON types.

### 5. Row capping for readability

Large tables are capped differently per format:

- **Markdown**: 50 rows max. Shows first 25, an ellipsis row (`| ... | ... |`), then last 5.
- **ASCII**: 30 rows max. Shows first 20, a summary line (`... (N more rows)`), then last 5.
- **JSON**: No cap. JSON is the machine-readable format; consumers can paginate or filter as needed.

The asymmetry is intentional: markdown documents are rendered in browsers/editors where 50 rows is scannable; ASCII output goes to terminals with limited vertical space; JSON is for programmatic consumption.

### 6. Deterministic output

Renderers never compute timestamps, read environment variables, or inject runtime state. The `generated_at` field is passed in via `OutputMetadata`. This means rendering the same `TechniqueResult` with the same `OutputMetadata` produces byte-identical output every time, which makes golden-file testing trivial and diffs meaningful.

### 7. ASCII sparklines

Sparklines use 8 Unicode block levels for compact trend visualization:

```
▁▂▃▄▅▆▇█
```

Values are linearly scaled between min and max of the input data. When the input has more data points than the requested width, values are downsampled by bin-averaging (each output character represents the mean of its bin). When all values are equal, the mid-level character (`▄`) is used throughout.

### 8. Re-exports in `mod.rs` for clean public API

The output module's `mod.rs` re-exports the key functions so callers use `output::render_markdown(...)` rather than `output::markdown::render_markdown(...)`:

```rust
pub use ascii::{render_ascii_bar, render_ascii_sparkline, render_ascii_table};
pub use json::render_json;
pub use markdown::render_markdown;
```

This gives internal organization (one file per format) with a flat external API.

## Why This Matters

The trait vs. function decision affects every downstream consumer. A poorly chosen trait abstraction would require callers to deal with associated types or match on enum variants for something that is inherently a static dispatch. Functions keep the code simple and make the API self-documenting: the function signature tells you exactly what goes in and what comes out.

## When to Apply

- Designing any multi-format output system where formats produce different types
- Evaluating whether to use a trait when the "implementations" don't share a return type
- Building renderers that need to be deterministic and testable
- Adding new output formats to an existing engine

## Examples

**Selecting a renderer based on CLI flags:**
```rust
match output_format {
    Format::Markdown => {
        let md = render_markdown(&result, &meta);
        std::fs::write(path, md)?;
    }
    Format::Json => {
        let json = render_json(&result, &meta);
        let pretty = serde_json::to_string_pretty(&json)?;
        std::fs::write(path, pretty)?;
    }
    Format::Ascii => {
        for table in &result.tables {
            println!("{}", render_ascii_table(table, 40));
        }
    }
}
```

**Adding a new renderer** requires only:
1. Create `src/output/new_format.rs`
2. Add `pub mod new_format;` and a `pub use` re-export in `mod.rs`
3. Add a match arm in the CLI dispatcher

No traits to implement, no registration, no type gymnastics.

## Related

- Implementation: `middens/src/output/mod.rs`, `middens/src/output/markdown.rs`, `middens/src/output/json.rs`, `middens/src/output/ascii.rs`
- TechniqueResult definition: `middens/src/techniques/mod.rs`
- Output engine plan: `docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md`
