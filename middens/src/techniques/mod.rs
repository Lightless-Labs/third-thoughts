//! Analytical techniques — both Rust-native and Python-bridged.

pub mod burstiness;
pub mod correction_rate;
pub mod diversity;
pub mod entropy;
pub mod markov;
pub mod thinking_divergence;

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::session::Session;

/// Result from running a technique.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TechniqueResult {
    /// Technique name.
    pub name: String,
    /// Human-readable summary of findings.
    pub summary: String,
    /// Key findings as name-value pairs.
    #[serde(default)]
    pub findings: Vec<Finding>,
    /// Raw data tables (for Parquet/JSON export).
    #[serde(default)]
    pub tables: Vec<DataTable>,
    /// Vega-Lite figure specifications.
    #[serde(default)]
    pub figures: Vec<FigureSpec>,
}

/// A single finding from a technique.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub label: String,
    pub value: serde_json::Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// Declared column type for Parquet serialisation and manifest metadata.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ColumnType {
    Int,
    Float,
    String,
    Bool,
    Timestamp,
}

/// Chart type for table-derived figures.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChartType {
    Line,
    Bar,
    Heatmap,
    Scatter,
    Histogram,
    Boxplot,
}

/// Kind of figure specification.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum FigureKind {
    VegaLite { spec: serde_json::Value },
    TableRef { chart_type: ChartType },
}

/// A data table for export.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataTable {
    pub name: String,
    pub columns: Vec<String>,
    pub rows: Vec<Vec<serde_json::Value>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub column_types: Option<Vec<ColumnType>>,
}

/// A figure specification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FigureSpec {
    pub title: String,
    pub kind: FigureKind,
}

/// Trait for analytical techniques.
pub trait Technique {
    /// Technique name (used in --techniques flag).
    fn name(&self) -> &str;

    /// Human-readable description.
    fn description(&self) -> &str;

    /// Whether this technique requires Python.
    fn requires_python(&self) -> bool;

    /// Whether this technique is in the essential 10.
    fn is_essential(&self) -> bool;

    /// Run the technique on the given sessions.
    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult>;

    /// Set a pre-written session cache file path. Techniques that support it
    /// (e.g. PythonTechnique) will read from this file instead of re-serializing
    /// the sessions on every call. Default: no-op (Rust techniques don't need it).
    fn set_session_cache(&mut self, _path: &std::path::Path) {}
}

/// All Rust-native techniques.
pub fn all_techniques() -> Vec<Box<dyn Technique>> {
    vec![
        Box::new(burstiness::Burstiness),
        Box::new(correction_rate::CorrectionRate),
        Box::new(diversity::Diversity),
        Box::new(entropy::EntropyRate),
        Box::new(markov::MarkovChain),
        Box::new(thinking_divergence::ThinkingDivergence),
    ]
}

/// Metadata for a Python-bridged technique: (name, description, script filename).
///
/// Script filename is resolved at runtime against the extracted scripts
/// directory (see `bridge::embedded::extract_to`). Keeping the list here
/// means registration is in sync with the embedded asset list.
pub const PYTHON_TECHNIQUE_MANIFEST: &[(&str, &str, &str)] = &[
    (
        "hsmm",
        "Hidden semi-Markov behavioural-state modelling",
        "hsmm.py",
    ),
    (
        "information-foraging",
        "Charnov marginal-value-theorem patch analysis",
        "information_foraging.py",
    ),
    (
        "granger-causality",
        "Granger causality between event streams",
        "granger_causality.py",
    ),
    (
        "survival-analysis",
        "Kaplan-Meier / Cox session survival",
        "survival_analysis.py",
    ),
    (
        "process-mining",
        "Directly-follows graph process discovery",
        "process_mining.py",
    ),
    (
        "prefixspan-mining",
        "PrefixSpan frequent sequential-pattern mining",
        "prefixspan_mining.py",
    ),
    (
        "smith-waterman",
        "Smith-Waterman local sequence alignment",
        "smith_waterman.py",
    ),
    (
        "tpattern-detection",
        "Magnusson T-pattern temporal detection",
        "tpattern_detection.py",
    ),
    (
        "lag-sequential",
        "Lag-sequential transition analysis",
        "lag_sequential.py",
    ),
    (
        "spc-control-charts",
        "Statistical process control charts",
        "spc_control_charts.py",
    ),
    (
        "ncd-clustering",
        "Normalised compression-distance clustering",
        "ncd_clustering.py",
    ),
    (
        "ena-analysis",
        "Epistemic network analysis",
        "ena_analysis.py",
    ),
    (
        "convention-epidemiology",
        "Convention-epidemiology diffusion model",
        "convention_epidemiology.py",
    ),
    (
        "user-signal-analysis",
        "User message signal classification (English-only)",
        "user_signal_analysis.py",
    ),
    (
        "cross-project-graph",
        "Directed reference graph between projects with centrality metrics",
        "cross_project_graph.py",
    ),
    (
        "change-point-detection",
        "Ruptures PELT regime-shift detection on per-session signals",
        "change_point_detection.py",
    ),
    (
        "corpus-timeline",
        "Per-day per-project session counts (provisional)",
        "corpus_timeline.py",
    ),
];

/// Build Python-bridged techniques from the manifest, resolving each
/// script against `scripts_dir` and using `python_path` as the interpreter.
pub fn python_techniques(
    scripts_dir: &std::path::Path,
    python_path: &std::path::Path,
    timeout_seconds: u64,
) -> Vec<Box<dyn Technique>> {
    use crate::bridge::PythonTechnique;
    PYTHON_TECHNIQUE_MANIFEST
        .iter()
        .map(|(name, desc, filename)| {
            Box::new(PythonTechnique::new(
                name,
                desc,
                scripts_dir.join(filename),
                python_path.to_path_buf(),
                timeout_seconds,
            )) as Box<dyn Technique>
        })
        .collect()
}

/// Rust techniques + Python techniques combined. Used by the analyze
/// pipeline when a Python environment has been successfully detected.
pub fn all_techniques_with_python(
    scripts_dir: &std::path::Path,
    python_path: &std::path::Path,
    timeout_seconds: u64,
) -> Vec<Box<dyn Technique>> {
    let mut t = all_techniques();
    t.extend(python_techniques(scripts_dir, python_path, timeout_seconds));
    t
}
