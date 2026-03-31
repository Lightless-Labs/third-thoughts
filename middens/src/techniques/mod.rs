//! Analytical techniques — both Rust-native and Python-bridged.

pub mod burstiness;
pub mod correction_rate;
pub mod diversity;
pub mod entropy;
pub mod markov;

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
    pub findings: Vec<Finding>,
    /// Raw data tables (for Parquet/JSON export).
    pub tables: Vec<DataTable>,
    /// Vega-Lite figure specifications.
    pub figures: Vec<FigureSpec>,
}

/// A single finding from a technique.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub label: String,
    pub value: serde_json::Value,
    pub description: Option<String>,
}

/// A data table for export.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataTable {
    pub name: String,
    pub columns: Vec<String>,
    pub rows: Vec<Vec<serde_json::Value>>,
}

/// A Vega-Lite figure specification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FigureSpec {
    pub title: String,
    pub spec: serde_json::Value,
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
}

/// All registered techniques.
pub fn all_techniques() -> Vec<Box<dyn Technique>> {
    vec![
        Box::new(burstiness::Burstiness),
        Box::new(correction_rate::CorrectionRate),
        Box::new(diversity::Diversity),
        Box::new(entropy::EntropyRate),
        Box::new(markov::MarkovChain),
    ]
}

