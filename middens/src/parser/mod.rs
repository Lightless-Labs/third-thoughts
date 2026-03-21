//! Pluggable parser architecture for multiple agent tool session log formats.

pub mod auto_detect;
pub mod claude_code;
pub mod codex;
pub mod gemini;
pub mod openclaw;

use std::path::Path;

use anyhow::Result;

use crate::session::{Session, SourceTool};

/// Trait that all session log parsers implement.
///
/// Adding support for a new agent tool format requires:
/// 1. Implement this trait in a new module
/// 2. Register it in `auto_detect::detect_and_parse`
pub trait SessionParser {
    /// Which tool this parser handles.
    fn source_tool(&self) -> SourceTool;

    /// Whether this parser can handle the given file.
    ///
    /// Implementations should check file structure (first line, extension,
    /// directory layout) without fully parsing the file.
    fn can_parse(&self, path: &Path) -> bool;

    /// Parse a session log file into one or more sessions.
    ///
    /// A single file may contain multiple sessions (e.g., OpenClaw per-agent files).
    fn parse(&self, path: &Path) -> Result<Vec<Session>>;
}

/// All available parsers.
pub fn all_parsers() -> Vec<Box<dyn SessionParser>> {
    vec![
        Box::new(claude_code::ClaudeCodeParser),
        Box::new(codex::CodexParser),
        Box::new(openclaw::OpenClawParser),
        Box::new(gemini::GeminiParser),
    ]
}
