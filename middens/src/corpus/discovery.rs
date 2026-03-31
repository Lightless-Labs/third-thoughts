//! Corpus discovery: find session log files across all supported agent tools.

use std::path::{Path, PathBuf};

use anyhow::Result;
use walkdir::WalkDir;

use crate::session::SourceTool;

/// Default locations for each supported agent tool's session logs.
const DEFAULT_DIRS: &[(SourceTool, &str)] = &[
    (SourceTool::ClaudeCode, ".claude/projects"),
    (SourceTool::CodexCli, ".codex/sessions"),
    (SourceTool::GeminiCli, ".gemini/history"),
    (SourceTool::OpenClaw, "openclaw-sessions"),
];

/// Recursively discover all `.jsonl` files under `path`.
///
/// If `path` is `None`, searches the default locations for each supported tool
/// under the user's home directory.
///
/// Follows symlinks so that linked corpus directories are included.
/// Reports what was found to stderr.
pub fn discover_sessions(path: Option<&Path>) -> Result<Vec<PathBuf>> {
    match path {
        Some(p) => discover_in_dir(p),
        None => discover_defaults(),
    }
}

/// Walk a single directory tree, collecting `.jsonl` files.
fn discover_in_dir(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();

    if !dir.exists() {
        eprintln!("middens: corpus path does not exist: {}", dir.display());
        return Ok(files);
    }

    for entry in WalkDir::new(dir).follow_links(true) {
        let entry = entry?;
        if entry.file_type().is_file() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("jsonl") {
                files.push(path.to_path_buf());
            }
        }
    }

    eprintln!(
        "middens: discovered {} session file(s) in {}",
        files.len(),
        dir.display()
    );
    Ok(files)
}

/// Check all default tool locations under `$HOME`.
fn discover_defaults() -> Result<Vec<PathBuf>> {
    let home = home_dir()?;
    let mut all_files = Vec::new();

    for &(tool, rel_path) in DEFAULT_DIRS {
        let dir = home.join(rel_path);
        if dir.exists() {
            let found = discover_in_dir(&dir)?;
            if !found.is_empty() {
                eprintln!(
                    "middens: found {} file(s) for {} in {}",
                    found.len(),
                    tool,
                    dir.display()
                );
            }
            all_files.extend(found);
        }
    }

    if all_files.is_empty() {
        eprintln!("middens: no session files found in any default location");
    } else {
        eprintln!(
            "middens: {} total session file(s) discovered across all tools",
            all_files.len()
        );
    }

    Ok(all_files)
}

/// Get the user's home directory.
///
/// Tries HOME first (Unix/macOS), then falls back to USERPROFILE (Windows).
/// This makes the function portable across platforms.
fn home_dir() -> Result<PathBuf> {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .map_err(|_| {
            anyhow::anyhow!(
                "could not determine home directory (neither HOME nor USERPROFILE is set)"
            )
        })
}
