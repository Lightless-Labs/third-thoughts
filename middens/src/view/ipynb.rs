use anyhow::Result;
use serde_json::{Value, json};

use crate::storage::{AnalysisRun, RedactionConfig};

use super::{ViewRenderer, markdown};

pub struct IpynbRenderer {
    pub interpretation_dir: Option<std::path::PathBuf>,
    pub redaction: RedactionConfig,
}

impl IpynbRenderer {
    pub fn new(redaction: RedactionConfig) -> Self {
        Self {
            interpretation_dir: None,
            redaction,
        }
    }

    pub fn with_interpretation(dir: std::path::PathBuf, redaction: RedactionConfig) -> Self {
        Self {
            interpretation_dir: Some(dir),
            redaction,
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

        execution_count += 1;
        cells.push(code_cell(
            "import os\nRUN_DIR = os.environ.get(\"MIDDENS_RUN_DIR\", os.getcwd())",
            execution_count,
            &[],
        ));

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
                     df_{slug} = pd.read_parquet(os.path.join(RUN_DIR, {path:?}))\n\
                     df_{slug}.head(10)",
                    slug = entry.name.replace('-', "_"),
                    path = table_ref.parquet,
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
            "analysis_run_path": self
                .redaction
                .analysis_run_path(&manifest.run_id, run.dir()),
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

#[cfg(test)]
mod tests {
    use super::IpynbRenderer;
    use crate::storage::{
        AnalysisManifest, AnalysisRun, AnalyzerFingerprint, CorpusFingerprint, ManifestWriter,
        ParquetWriter, RedactionConfig, TableRef, TechniqueEntry,
    };
    use crate::techniques::{ColumnType, DataTable};
    use crate::view::ViewRenderer;
    use chrono::{DateTime, Utc};
    use serde_json::{Value, json};
    use std::collections::BTreeMap;

    fn write_test_run() -> AnalysisRun {
        let dir = tempfile::tempdir().unwrap();
        let run_dir = dir.path().join("run-test");
        std::fs::create_dir_all(run_dir.join("data")).unwrap();

        let table = DataTable {
            name: "per_session".into(),
            columns: vec!["session_id".into()],
            rows: vec![vec![json!("session-1")]],
            column_types: Some(vec![ColumnType::String]),
        };
        ParquetWriter::write_table(
            &table,
            "test-technique",
            &run_dir.join("data/test-technique.parquet"),
        )
        .unwrap();

        let manifest = AnalysisManifest {
            run_id: "run-test".into(),
            created_at: DateTime::parse_from_rfc3339("2026-04-18T00:00:00Z")
                .unwrap()
                .with_timezone(&Utc),
            analyzer_fingerprint: AnalyzerFingerprint {
                middens_version: "0.1.0".into(),
                git_sha: None,
                technique_versions: BTreeMap::from([(
                    "test-technique".to_string(),
                    "0.1.0".to_string(),
                )]),
                python_bridge: None,
            },
            corpus_fingerprint: CorpusFingerprint {
                manifest_hash: "abc".into(),
                short: "abc".into(),
                session_count: 1,
                source_paths: vec!["session-a.jsonl".into()],
            },
            strata: None,
            stratum: None,
            techniques: vec![TechniqueEntry {
                name: "test-technique".into(),
                version: "0.1.0".into(),
                summary: "summary".into(),
                findings: vec![],
                table: Some(TableRef {
                    name: "per_session".into(),
                    parquet: "data/test-technique.parquet".into(),
                    row_count: 1,
                    column_types: Some(vec![ColumnType::String]),
                }),
                figures: vec![],
                errors: vec![],
            }],
        };
        ManifestWriter::write(&manifest, &run_dir.join("manifest.json")).unwrap();

        let run = AnalysisRun::load(&run_dir).unwrap();
        std::mem::forget(dir);
        run
    }

    #[test]
    fn render_run_includes_setup_cell_when_scrubbing_paths() {
        let run = write_test_run();
        let notebook = IpynbRenderer::new(RedactionConfig::default())
            .render_run(&run)
            .unwrap();
        let notebook: Value = serde_json::from_str(&notebook).unwrap();

        let first_code_cell = notebook["cells"]
            .as_array()
            .unwrap()
            .iter()
            .find(|cell| cell["cell_type"] == "code")
            .unwrap();
        let first_code_source = first_code_cell["source"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|line| line.as_str())
            .collect::<String>();
        assert!(first_code_source.contains("MIDDENS_RUN_DIR"));

        let table_code_source = notebook["cells"]
            .as_array()
            .unwrap()
            .iter()
            .find(|cell| {
                cell["cell_type"] == "code"
                    && cell["source"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(|line| line.as_str())
                        .collect::<String>()
                        .contains("pd.read_parquet")
            })
            .unwrap()["source"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|line| line.as_str())
            .collect::<String>();
        assert!(
            table_code_source.contains("os.path.join(RUN_DIR, \"data/test-technique.parquet\")")
        );
        assert_eq!(
            notebook["metadata"]["middens"]["analysis_run_path"],
            json!("analysis/run-test")
        );
    }
}
