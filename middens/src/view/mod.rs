//! View layer — renderers that turn stored analysis runs into human-readable output.
//!
//! Every presentation format is a pure function of storage ([AnalysisRun]). The
//! [ViewRenderer] trait defines the interface; concrete renderers implement it.

pub mod ascii;
pub mod ipynb;
pub mod json;
pub mod markdown;

use std::collections::BTreeMap;

use anyhow::Result;

use crate::storage::AnalysisRun;
use crate::techniques::TechniqueResult;

#[derive(Debug, Clone)]
pub struct OutputMetadata {
    pub technique_name: String,
    pub corpus_size: u64,
    pub generated_at: String,
    pub middens_version: String,
    pub parameters: BTreeMap<String, String>,
}

pub trait ViewRenderer {
    fn render_run(&self, run: &AnalysisRun) -> Result<String>;
}

pub trait TechniqueViewRenderer {
    fn render(&self, result: &TechniqueResult, meta: &OutputMetadata) -> String;
}

pub use ascii::{render_ascii_bar, render_ascii_sparkline, render_ascii_table};
pub use json::render_json;
pub use markdown::render_markdown;
