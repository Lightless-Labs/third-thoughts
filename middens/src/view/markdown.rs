use crate::storage::AnalysisRun;
use crate::techniques::{DataTable, TechniqueResult};

use super::{OutputMetadata, TechniqueViewRenderer, ViewRenderer};

fn quote_yaml_string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

pub fn format_value(value: &serde_json::Value) -> String {
    let formatted = match value {
        serde_json::Value::Null => "\u{2014}".to_string(),
        serde_json::Value::Bool(true) => "yes".to_string(),
        serde_json::Value::Bool(false) => "no".to_string(),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else if let Some(f) = n.as_f64() {
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
        other => serde_json::to_string(other).unwrap_or_default(),
    };

    formatted.replace('|', "\\|").replace('\n', " ")
}

pub fn render_markdown_table(table: &DataTable) -> String {
    let mut output = String::new();

    output.push('|');
    for col in &table.columns {
        output.push(' ');
        output.push_str(col);
        output.push_str(" |");
    }
    output.push('\n');

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
        for row in &table.rows[..25] {
            output.push('|');
            for val in row {
                output.push(' ');
                output.push_str(&format_value(val));
                output.push_str(" |");
            }
            output.push('\n');
        }

        output.push('|');
        for _ in &table.columns {
            output.push_str(" ... |");
        }
        output.push('\n');

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

pub fn render_markdown(result: &TechniqueResult, meta: &OutputMetadata) -> String {
    let mut output = String::new();

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

    output.push_str(&format!("# {}\n\n", result.name));
    if !result.summary.is_empty() {
        output.push_str(&result.summary);
        output.push_str("\n\n");
    }

    if !result.findings.is_empty() {
        output.push_str("## Findings\n\n");
        output.push_str("| Finding | Value | Description |\n");
        output.push_str("|---------|-------|-------------|\n");
        for finding in &result.findings {
            let label = finding.label.replace('|', "\\|").replace('\n', " ");
            let desc = finding
                .description
                .as_deref()
                .unwrap_or("")
                .replace('|', "\\|")
                .replace('\n', " ");
            output.push_str(&format!(
                "| {} | {} | {} |\n",
                label,
                format_value(&finding.value),
                desc
            ));
        }
        output.push('\n');
    }

    for table in &result.tables {
        output.push_str(&format!("## {}\n\n", table.name));
        output.push_str(&render_markdown_table(table));
        output.push('\n');
    }

    for figure in &result.figures {
        output.push_str(&format!("## {}\n\n", figure.title));
        output.push_str("```json\n");
        output.push_str(&serde_json::to_string_pretty(&figure.kind).unwrap_or_default());
        output.push_str("\n```\n\n");
    }

    output
}

pub struct MarkdownRenderer;

impl TechniqueViewRenderer for MarkdownRenderer {
    fn render(&self, result: &TechniqueResult, meta: &OutputMetadata) -> String {
        render_markdown(result, meta)
    }
}

impl ViewRenderer for MarkdownRenderer {
    fn render_run(&self, run: &AnalysisRun) -> anyhow::Result<String> {
        let manifest = run.manifest();
        let mut output = String::new();

        output.push_str(&format!("# Analysis Run: {}\n\n", manifest.run_id));
        output.push_str(&format!(
            "Created: {}\n\n",
            manifest.created_at.to_rfc3339()
        ));
        output.push_str(&format!(
            "Corpus fingerprint: {} ({} sessions)\n\n",
            manifest.corpus_fingerprint.short, manifest.corpus_fingerprint.session_count
        ));
        output.push_str(&format!(
            "Middens version: {}\n\n",
            manifest.analyzer_fingerprint.middens_version
        ));

        for entry in &manifest.techniques {
            output.push_str(&format!("## {}\n\n", entry.name));
            if !entry.summary.is_empty() {
                output.push_str(&entry.summary);
                output.push_str("\n\n");
            }

            if !entry.findings.is_empty() {
                output.push_str("| Finding | Value | Description |\n");
                output.push_str("|---------|-------|-------------|\n");
                for finding in &entry.findings {
                    let label = finding.label.replace('|', "\\|").replace('\n', " ");
                    let desc = finding
                        .description
                        .as_deref()
                        .unwrap_or("")
                        .replace('|', "\\|")
                        .replace('\n', " ");
                    output.push_str(&format!(
                        "| {} | {} | {} |\n",
                        label,
                        format_value(&finding.value),
                        desc
                    ));
                }
                output.push('\n');
            }

            if let Some(table_ref) = &entry.table {
                if let Ok(table) = run.load_table(table_ref) {
                    output.push_str(&format!("### {}\n\n", table_ref.name));
                    output.push_str(&render_markdown_table(&table));
                    output.push('\n');
                }
            }

            if !entry.errors.is_empty() {
                output.push_str("**Errors:**\n");
                for err in &entry.errors {
                    output.push_str(&format!("- {}\n", err));
                }
                output.push('\n');
            }
        }

        Ok(output)
    }
}
