//! Output engine — ASCII, JSON, and Markdown renderers.

pub mod ascii;
pub mod json;
pub mod markdown;

use std::collections::BTreeMap;

/// Metadata about the output context (technique, corpus, version, etc.).
#[derive(Debug, Clone)]
pub struct OutputMetadata {
    pub technique_name: String,
    pub corpus_size: u64,
    pub generated_at: String,
    pub middens_version: String,
    pub parameters: BTreeMap<String, String>,
}

pub use ascii::{render_ascii_bar, render_ascii_sparkline, render_ascii_table};
pub use json::render_json;
pub use markdown::render_markdown;
