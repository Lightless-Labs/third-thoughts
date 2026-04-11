use anyhow::Result;
use serde_json::{json, Value};

use crate::storage::AnalysisRun;

use super::{markdown, ViewRenderer};

pub struct IpynbRenderer {
    pub interpretation_dir: Option<std::path::PathBuf>,
}

impl IpynbRenderer {
    pub fn new() -> Self {
        Self {
            interpretation_dir: None,
        }
    }

    pub fn with_interpretation(dir: std::path::PathBuf) -> Self {
        Self {
            interpretation_dir: Some(dir),
        }
    }
}

impl ViewRenderer for IpynbRenderer {
    fn render_run(&self, run: &AnalysisRun) -> Result<String> {
        let manifest = run.manifest();
        let mut cells: Vec<Value> = Vec::new();
        let mut execution_count: i64 = 0;

        cells.push(md_cell(format!(
            "# Analysis Report: {}\n\n\
             **Created:** {}\n  \
             **Sessions:** {}\n\
             **Corpus fingerprint:** {}",
            manifest.run_id,
            manifest.created_at.to_rfc3339(),
            manifest.corpus_fingerprint.session_count,
            manifest.corpus_fingerprint.short,
        )));

        cells.push(md_cell(format!(
            "## Analyzer Fingerprint\n\n\
             - **Middens version:** {}\n\
             - **Git SHA:** {}",
            manifest.analyzer_fingerprint.middens_version,
            manifest
                .analyzer_fingerprint
                .git_sha
                .as_deref()
                .unwrap_or("N/A"),
        )));

        if let Some(ref interp_dir) = self.interpretation_dir {
            if let Ok(conclusions) = std::fs::read_to_string(interp_dir.join("conclusions.md")) {
                if !conclusions.trim().is_empty() {
                    cells.push(md_cell(format!("## Conclusions\n\n{}", conclusions)));
                }
            }
        }

        for entry in &manifest.techniques {
            let mut technique_md = format!("## Technique: {}\n\n", entry.name);
            if !entry.summary.is_empty() {
                technique_md.push_str(&entry.summary);
                technique_md.push_str("\n\n");
            }

            if !entry.findings.is_empty() {
                technique_md.push_str("| Finding | Value | Description |\n");
                technique_md.push_str("|---------|-------|-------------|\n");
                for finding in &entry.findings {
                    let label = finding.label.replace('|', "\\|").replace('\n', " ");
                    let desc = finding
                        .description
                        .as_deref()
                        .unwrap_or("")
                        .replace('|', "\\|")
                        .replace('\n', " ");
                    technique_md.push_str(&format!(
                        "| {} | {} | {} |\n",
                        label,
                        markdown::format_value(&finding.value),
                        desc
                    ));
                }
                technique_md.push('\n');
            }

            cells.push(md_cell(technique_md));

            if let Some(table_ref) = &entry.table {
                execution_count += 1;
                let code = format!(
                    "import pandas as pd\n\
                     df_{slug} = pd.read_parquet({path:?})\n\
                     df_{slug}.head(10)",
                    slug = entry.name.replace('-', "_"),
                    path = run.dir().join(&table_ref.parquet).display(),
                );
                let mut outputs = Vec::new();
                let table = run.load_table(table_ref)?;
                {
                    let head_rows = table.rows.len().min(10);
                    let mut html = String::from("<table>\n<thead>\n<tr>");
                    for col in &table.columns {
                        html.push_str(&format!("<th>{}</th>", html_escape(col)));
                    }
                    html.push_str("</tr>\n</thead>\n<tbody>\n");
                    for row in &table.rows[..head_rows] {
                        html.push_str("<tr>");
                        for val in row {
                            html.push_str(&format!(
                                "<td>{}</td>",
                                html_escape(&markdown::format_value(val))
                            ));
                        }
                        html.push_str("</tr>\n");
                    }
                    html.push_str("</tbody>\n</table>");

                    let mut plain = String::new();
                    for col in &table.columns {
                        if !plain.is_empty() {
                            plain.push_str("  ");
                        }
                        plain.push_str(col);
                    }
                    plain.push('\n');
                    for row in &table.rows[..head_rows] {
                        let mut first = true;
                        for val in row {
                            if !first {
                                plain.push_str("  ");
                            }
                            first = false;
                            plain.push_str(&markdown::format_value(val));
                        }
                        plain.push('\n');
                    }

                    outputs.push(json!({
                        "output_type": "display_data",
                        "data": {
                            "text/html": html,
                            "text/plain": plain,
                        },
                        "metadata": {},
                    }));
                }

                cells.push(code_cell(&code, execution_count, &outputs));

                if let Some(ref interp_dir) = self.interpretation_dir {
                    let conc_path = interp_dir.join(format!("{}-conclusions.md", entry.name));
                    if let Ok(content) = std::fs::read_to_string(&conc_path) {
                        if !content.trim().is_empty() {
                            cells.push(md_cell(format!(
                                "### Interpretation: {}\n\n{}",
                                entry.name, content
                            )));
                        }
                    }
                }

                let starter = format!(
                    "# Exploratory analysis for {name}\n\
                     # df_{slug}.describe()\n\
                     # df_{slug}.corr(numeric_only=True)",
                    name = entry.name,
                    slug = entry.name.replace('-', "_"),
                );
                execution_count += 1;
                cells.push(code_cell(&starter, execution_count, &[]));
            }

            if !entry.errors.is_empty() {
                let mut err_md = String::from("**Errors:**\n\n");
                for err in &entry.errors {
                    err_md.push_str(&format!("- {}\n", err));
                }
                cells.push(md_cell(err_md));
            }
        }

        let mut middens_meta = json!({
            "analysis_run_id": manifest.run_id,
            "analysis_run_path": run.dir().display().to_string(),
            "middens_version": manifest.analyzer_fingerprint.middens_version,
        });

        if let Some(ref interp_dir) = self.interpretation_dir {
            if let Ok(interp_manifest_raw) =
                std::fs::read_to_string(interp_dir.join("manifest.json"))
            {
                if let Ok(interp_manifest) =
                    serde_json::from_str::<serde_json::Value>(&interp_manifest_raw)
                {
                    if let Some(id) = interp_manifest
                        .get("interpretation_id")
                        .and_then(|v| v.as_str())
                    {
                        middens_meta
                            .as_object_mut()
                            .unwrap()
                            .insert("interpretation_id".into(), json!(id));
                    }
                    middens_meta.as_object_mut().unwrap().insert(
                        "interpretation_path".into(),
                        json!(interp_dir.display().to_string()),
                    );
                }
            }
        }

        let notebook = json!({
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {
                    "name": "python",
                    "version": "3.12.0",
                    "mimetype": "text/x-python",
                    "codemirror_mode": { "name": "ipython", "version": 3 },
                    "file_extension": ".py",
                },
                "middens": middens_meta,
            },
            "cells": cells,
        });

        Ok(serde_json::to_string_pretty(&notebook)?)
    }
}

fn md_cell(source: String) -> Value {
    json!({
        "cell_type": "markdown",
        "metadata": {},
        "source": split_lines(&source),
    })
}

fn code_cell(code: &str, execution_count: i64, outputs: &[Value]) -> Value {
    json!({
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "source": split_lines(code),
        "outputs": outputs,
    })
}

fn split_lines(s: &str) -> Vec<Value> {
    s.lines()
        .flat_map(|line| {
            let mut v = Vec::new();
            v.push(json!(format!("{}\n", line)));
            v
        })
        .collect::<Vec<_>>()
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}
