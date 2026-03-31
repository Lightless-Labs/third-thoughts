//! Corpus manifest: freeze a snapshot of corpus contents for reproducibility.

use std::fs;
use std::io::Read;
use std::path::Path;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use walkdir::WalkDir;

use crate::session::SourceTool;

/// A single entry in the corpus manifest.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestEntry {
    /// Absolute path to the session file.
    pub path: String,
    /// File size in bytes.
    pub size: u64,
    /// SHA-256 hex digest of the file contents.
    pub sha256: String,
    /// Which tool produced this session (best guess from path).
    pub tool: SourceTool,
}

/// Full corpus manifest.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    /// ISO-8601 timestamp of when this manifest was created.
    pub created_at: String,
    /// Entries for each file in the corpus.
    pub entries: Vec<ManifestEntry>,
}

/// Walk the corpus at `path`, record each file's path, size, and SHA-256 hash,
/// then write the manifest as JSON to `output`.
pub fn create_manifest(path: &Path, output: &Path) -> Result<()> {
    let mut entries = Vec::new();

    for entry in WalkDir::new(path).follow_links(true) {
        let entry = entry?;
        if !entry.file_type().is_file() {
            continue;
        }
        let file_path = entry.path();
        if file_path.extension().and_then(|e| e.to_str()) != Some("jsonl") {
            continue;
        }

        let metadata = fs::metadata(file_path)
            .with_context(|| format!("reading metadata for {}", file_path.display()))?;

        let sha256 = hash_file(file_path)?;
        let tool = guess_tool_from_path(file_path);

        entries.push(ManifestEntry {
            path: file_path.to_string_lossy().into_owned(),
            size: metadata.len(),
            sha256,
            tool,
        });
    }

    let manifest = Manifest {
        created_at: chrono::Utc::now().to_rfc3339(),
        entries,
    };

    let json = serde_json::to_string_pretty(&manifest)?;
    fs::write(output, json)
        .with_context(|| format!("writing manifest to {}", output.display()))?;

    eprintln!(
        "middens: manifest written to {} ({} entries)",
        output.display(),
        manifest.entries.len()
    );

    Ok(())
}

/// Compute the SHA-256 hex digest of a file.
pub fn hash_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path)
        .with_context(|| format!("opening {} for hashing", path.display()))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// Best-effort guess of which tool produced a file based on its path.
fn guess_tool_from_path(path: &Path) -> SourceTool {
    let s = path.to_string_lossy();
    if s.contains(".claude") {
        SourceTool::ClaudeCode
    } else if s.contains(".codex") {
        SourceTool::CodexCli
    } else if s.contains(".gemini") {
        SourceTool::GeminiCli
    } else if s.contains("openclaw") {
        SourceTool::OpenClaw
    } else {
        SourceTool::Unknown
    }
}
