use std::path::PathBuf;

use cucumber::World;
use tempfile::TempDir;

use middens::session::{MessageClassification, Session, SessionType, SourceTool};
use middens::techniques::TechniqueResult;

/// Shared test state for all Cucumber scenarios.
///
/// A fresh `MiddensWorld` is constructed for every scenario — no cross-scenario state leakage.
#[derive(Debug, World)]
#[world(init = Self::new)]
pub struct MiddensWorld {
    /// Parsed sessions (output of parser / input to techniques).
    pub sessions: Vec<Session>,
    /// Result from running a technique.
    pub technique_result: Option<TechniqueResult>,
    /// Detected source tool format.
    pub detected_format: Option<SourceTool>,
    /// Classified session type.
    pub classified_type: Option<SessionType>,
    /// Classified message type.
    pub classified_message: Option<MessageClassification>,
    /// CLI command stdout output.
    pub cli_output: String,
    /// CLI command stderr output.
    pub cli_stderr: String,
    /// CLI exit code.
    pub cli_exit_code: Option<i32>,
    /// Temporary directory for filesystem tests.
    pub temp_dir: Option<TempDir>,
    /// Path to a file being tested.
    pub file_path: Option<PathBuf>,
    /// Path to an output file.
    pub output_path: Option<PathBuf>,
    /// Error captured during an operation.
    pub error: Option<String>,
    /// Discovered file paths.
    pub discovered_files: Vec<PathBuf>,
    /// Generic numeric result for assertions.
    pub numeric_result: Option<f64>,
    /// Whether the scenario was skipped due to environment constraints.
    pub skipped: bool,
}

impl MiddensWorld {
    fn new() -> Self {
        Self {
            sessions: Vec::new(),
            technique_result: None,
            detected_format: None,
            classified_type: None,
            classified_message: None,
            cli_output: String::new(),
            cli_stderr: String::new(),
            cli_exit_code: None,
            temp_dir: None,
            file_path: None,
            output_path: None,
            error: None,
            discovered_files: Vec::new(),
            numeric_result: None,
            skipped: false,
        }
    }
}
