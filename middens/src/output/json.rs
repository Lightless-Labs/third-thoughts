//! JSON renderer for technique results.

use serde_json::{json, Value};

use crate::techniques::TechniqueResult;

use super::OutputMetadata;

/// Render a `TechniqueResult` as a JSON `Value` with metadata envelope.
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
