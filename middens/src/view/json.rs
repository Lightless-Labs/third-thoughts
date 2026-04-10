use serde_json::{json, Value};

use crate::storage::AnalysisRun;
use crate::techniques::TechniqueResult;

use super::{OutputMetadata, TechniqueViewRenderer, ViewRenderer};

pub fn render_json(result: &TechniqueResult, meta: &OutputMetadata) -> Value {
    json!({
        "metadata": {
            "technique": meta.technique_name,
            "corpus_size": meta.corpus_size,
            "generated_at": meta.generated_at,
            "middens_version": meta.middens_version,
            "parameters": meta.parameters
        },
        "name": result.name,
        "summary": result.summary,
        "findings": result.findings,
        "tables": result.tables,
        "figures": result.figures
    })
}

pub struct JsonRenderer;

impl TechniqueViewRenderer for JsonRenderer {
    fn render(&self, result: &TechniqueResult, meta: &OutputMetadata) -> String {
        serde_json::to_string_pretty(&render_json(result, meta)).unwrap_or_default()
    }
}

impl ViewRenderer for JsonRenderer {
    fn render_run(&self, run: &AnalysisRun) -> anyhow::Result<String> {
        let manifest = run.manifest();
        let mut techniques = Vec::new();
        for entry in &manifest.techniques {
            let table_data = if let Some(table_ref) = &entry.table {
                run.load_table(table_ref).ok().map(|t| {
                    json!({
                        "name": t.name,
                        "columns": t.columns,
                        "rows": t.rows,
                        "column_types": t.column_types,
                    })
                })
            } else {
                None
            };

            techniques.push(json!({
                "name": entry.name,
                "version": entry.version,
                "summary": entry.summary,
                "findings": entry.findings,
                "table": table_data,
                "figures": entry.figures,
                "errors": entry.errors,
            }));
        }

        let doc = json!({
            "run_id": manifest.run_id,
            "created_at": manifest.created_at.to_rfc3339(),
            "analyzer_fingerprint": manifest.analyzer_fingerprint,
            "corpus_fingerprint": manifest.corpus_fingerprint,
            "techniques": techniques,
        });

        Ok(serde_json::to_string_pretty(&doc)?)
    }
}
