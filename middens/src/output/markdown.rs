//! Markdown renderer for technique results.

use crate::techniques::{DataTable, TechniqueResult};

use super::OutputMetadata;

fn quote_yaml_string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

/// Format a JSON value for display in markdown tables.
pub fn format_value(value: &serde_json::Value) -> String {
    let formatted = match value {
        serde_json::Value::Null => "\u{2014}".to_string(), // em dash
        serde_json::Value::Bool(true) => "yes".to_string(),
        serde_json::Value::Bool(false) => "no".to_string(),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else if let Some(f) = n.as_f64() {
                // Check if it's effectively an integer (no fractional part)
                if f.fract() == 0.0 && f.is_finite() {
                    format!("{:.0}", f)
                } else {
                    format!("{:.4}", f)
                }
            } else {
                n.to_string()
            }
        }
        serde_json::Value::String(s) => s.clone(),
        // array/object -> compact JSON
        other => serde_json::to_string(other).unwrap_or_default(),
    };

    formatted.replace('|', "\\|").replace('\n', " ")
}

/// Render a `DataTable` as a markdown table string.
pub fn render_markdown_table(table: &DataTable) -> String {
    let mut output = String::new();

    // Header row
    output.push('|');
    for col in &table.columns {
        output.push(' ');
        output.push_str(col);
        output.push_str(" |");
    }
    output.push('\n');

    // Separator row
    output.push('|');
    for col in &table.columns {
        let width = col.len().max(3);
        output.push_str(&"-".repeat(width + 2));
        output.push('|');
    }
    output.push('\n');

    let total_rows = table.rows.len();
    let cap = 50;

    if total_rows <= cap {
        // Render all rows
        for row in &table.rows {
            output.push('|');
            for val in row {
                output.push(' ');
                output.push_str(&format_value(val));
                output.push_str(" |");
            }
            output.push('\n');
        }
    } else {
        // First 25 rows
        for row in &table.rows[..25] {
            output.push('|');
            for val in row {
                output.push(' ');
                output.push_str(&format_value(val));
                output.push_str(" |");
            }
            output.push('\n');
        }

        // Ellipsis row
        output.push('|');
        for _ in &table.columns {
            output.push_str(" ... |");
        }
        output.push('\n');

        // Last 5 rows
        for row in &table.rows[total_rows - 5..] {
            output.push('|');
            for val in row {
                output.push(' ');
                output.push_str(&format_value(val));
                output.push_str(" |");
            }
            output.push('\n');
        }
    }

    output
}

/// Render a `TechniqueResult` as a full markdown document with YAML frontmatter.
pub fn render_markdown(result: &TechniqueResult, meta: &OutputMetadata) -> String {
    let mut output = String::new();

    // Step 1: YAML frontmatter
    output.push_str("---\n");
    output.push_str(&format!("technique: {}\n", meta.technique_name));
    output.push_str(&format!("corpus_size: {}\n", meta.corpus_size));
    output.push_str(&format!(
        "generated_at: {}\n",
        quote_yaml_string(&meta.generated_at)
    ));
    output.push_str(&format!(
        "middens_version: {}\n",
        quote_yaml_string(&meta.middens_version)
    ));
    if !meta.parameters.is_empty() {
        output.push_str("parameters:\n");
        for (key, value) in &meta.parameters {
            output.push_str(&format!("  {}: {}\n", key, quote_yaml_string(value)));
        }
    }
    output.push_str("---\n\n");

    // Step 2: Title and summary
    output.push_str(&format!("# {}\n\n", result.name));
    if !result.summary.is_empty() {
        output.push_str(&result.summary);
        output.push_str("\n\n");
    }

    // Step 3: Findings section
    if !result.findings.is_empty() {
        output.push_str("## Findings\n\n");
        output.push_str("| Finding | Value | Description |\n");
        output.push_str("|---------|-------|-------------|\n");
        for finding in &result.findings {
            let label = finding.label.replace('|', "\\|").replace('\n', " ");
            let desc = finding.description.as_deref().unwrap_or("")
                .replace('|', "\\|").replace('\n', " ");
            output.push_str(&format!(
                "| {} | {} | {} |\n",
                label,
                format_value(&finding.value),
                desc
            ));
        }
        output.push('\n');
    }

    // Step 4: Data tables
    for table in &result.tables {
        output.push_str(&format!("## {}\n\n", table.name));
        output.push_str(&render_markdown_table(table));
        output.push('\n');
    }

    // Step 5: Figures (as JSON code blocks)
    for figure in &result.figures {
        output.push_str(&format!("## {}\n\n", figure.title));
        output.push_str("```json\n");
        output.push_str(&serde_json::to_string_pretty(&figure.spec).unwrap_or_default());
        output.push_str("\n```\n\n");
    }

    output
}
