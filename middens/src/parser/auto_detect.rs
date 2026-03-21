//! Format auto-detection and dispatch for session log files.

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

use anyhow::{Context, Result};

use crate::session::{Session, SourceTool};

use super::all_parsers;

/// Detect which agent tool produced the given session log file.
///
/// Reads the first line and checks for format-specific signals:
/// - Claude Code: `{"type":"summary",...}` or `{"parentUuid":...}` patterns
/// - Codex CLI: `{"id":..., "model":...}` with OpenAI-style structure
/// - Gemini CLI: fields specific to Gemini history format
/// - OpenClaw: `{"session":...}` or OpenClaw-specific markers
///
/// Falls back to path-based heuristics if the first line is ambiguous.
pub fn detect_format(path: &Path) -> Option<SourceTool> {
    // Try first-line content detection.
    if let Some(tool) = detect_from_first_line(path) {
        return Some(tool);
    }

    // Fall back to path-based heuristics.
    detect_from_path(path)
}

/// Auto-detect the format of a session log file and parse it.
///
/// Tries each registered parser's `can_parse` method first, then falls back
/// to `detect_format` heuristics.
pub fn parse_auto(path: &Path) -> Result<Vec<Session>> {
    let parsers = all_parsers();

    // First pass: let each parser decide if it can handle this file.
    for parser in &parsers {
        if parser.can_parse(path) {
            return parser
                .parse(path)
                .with_context(|| format!("{} parser failed on {}", parser.source_tool(), path.display()));
        }
    }

    // Second pass: use format detection to pick a parser.
    if let Some(tool) = detect_format(path) {
        for parser in &parsers {
            if parser.source_tool() == tool {
                return parser
                    .parse(path)
                    .with_context(|| format!("{} parser failed on {}", tool, path.display()));
            }
        }
    }

    // No parser matched — return empty rather than erroring, so bulk
    // operations can continue with other files.
    eprintln!(
        "middens: no parser matched for {}, skipping",
        path.display()
    );
    Ok(vec![])
}

/// Attempt to detect the source tool by inspecting the first line of the file.
fn detect_from_first_line(path: &Path) -> Option<SourceTool> {
    let file = File::open(path).ok()?;
    let reader = BufReader::new(file);
    let first_line = reader.lines().next()?.ok()?;

    if first_line.is_empty() {
        return None;
    }

    // Try parsing as JSON to inspect fields.
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(&first_line) {
        return detect_from_json(&value);
    }

    None
}

/// Detect source tool from a parsed JSON first-line value.
fn detect_from_json(value: &serde_json::Value) -> Option<SourceTool> {
    let obj = value.as_object()?;

    // Claude Code signals: "type" field with "summary" value, or "parentUuid" field,
    // or a "uuid" + "type" combo.
    if obj.contains_key("parentUuid") || obj.contains_key("parentMessageUuid") {
        return Some(SourceTool::ClaudeCode);
    }
    if let Some(t) = obj.get("type").and_then(|v| v.as_str()) {
        if t == "summary" || t == "human" || t == "assistant" {
            return Some(SourceTool::ClaudeCode);
        }
    }

    // Codex CLI signals: "model" at top level with OpenAI-style IDs.
    if obj.contains_key("model") && obj.contains_key("id") {
        if let Some(model) = obj.get("model").and_then(|v| v.as_str()) {
            if model.starts_with("gpt") || model.starts_with("o1") || model.starts_with("o3") || model.starts_with("o4") || model.contains("codex") {
                return Some(SourceTool::CodexCli);
            }
        }
    }

    // Gemini CLI signals.
    if obj.contains_key("gemini") || obj.contains_key("generationConfig") {
        return Some(SourceTool::GeminiCli);
    }

    // OpenClaw signals.
    if obj.contains_key("session") || obj.contains_key("openclaw") {
        return Some(SourceTool::OpenClaw);
    }

    None
}

/// Detect source tool from the file path.
fn detect_from_path(path: &Path) -> Option<SourceTool> {
    let s = path.to_string_lossy();
    if s.contains(".claude") {
        Some(SourceTool::ClaudeCode)
    } else if s.contains(".codex") {
        Some(SourceTool::CodexCli)
    } else if s.contains(".gemini") {
        Some(SourceTool::GeminiCli)
    } else if s.contains("openclaw") {
        Some(SourceTool::OpenClaw)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn detect_claude_code_from_first_line() {
        let tmp = TempDir::new().unwrap();
        let file = tmp.path().join("session.jsonl");
        fs::write(&file, r#"{"parentUuid":"root","type":"human","text":"hello"}"#).unwrap();

        assert_eq!(detect_format(&file), Some(SourceTool::ClaudeCode));
    }

    #[test]
    fn detect_from_path_claude() {
        let path = Path::new("/home/user/.claude/projects/foo/session.jsonl");
        assert_eq!(detect_from_path(path), Some(SourceTool::ClaudeCode));
    }

    #[test]
    fn detect_from_path_codex() {
        let path = Path::new("/home/user/.codex/sessions/abc.jsonl");
        assert_eq!(detect_from_path(path), Some(SourceTool::CodexCli));
    }

    #[test]
    fn detect_from_path_gemini() {
        let path = Path::new("/home/user/.gemini/history/session.jsonl");
        assert_eq!(detect_from_path(path), Some(SourceTool::GeminiCli));
    }

    #[test]
    fn detect_from_path_openclaw() {
        let path = Path::new("/home/user/openclaw-sessions/run.jsonl");
        assert_eq!(detect_from_path(path), Some(SourceTool::OpenClaw));
    }

    #[test]
    fn detect_unknown_path() {
        let path = Path::new("/tmp/random/session.jsonl");
        assert_eq!(detect_from_path(path), None);
    }

    #[test]
    fn parse_auto_returns_empty_for_unknown() {
        let tmp = TempDir::new().unwrap();
        let file = tmp.path().join("mystery.jsonl");
        fs::write(&file, r#"{"unknown":"format"}"#).unwrap();

        let result = parse_auto(&file).unwrap();
        assert!(result.is_empty());
    }
}
