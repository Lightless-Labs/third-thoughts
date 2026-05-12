//! Format auto-detection and dispatch for session log files.

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

use anyhow::{Context, Result};

use crate::classifier::correction::classify_message;
use crate::classifier::session_type::classify_session;
use crate::session::{Session, SourceTool};

use super::all_parsers;

/// Detect which agent tool produced the given session log file.
///
/// Reads the first line and checks for format-specific signals:
/// - Claude Code: `{"type":"summary",...}` or `{"parentUuid":...}` patterns
/// - Codex CLI: `{"id":..., "model":...}` with OpenAI-style structure
/// - Gemini CLI: fields specific to Gemini history format
/// - Pi Coding Agent: `{"type":"session", "version": 3, ...}` session headers
/// - OpenClaw: OpenClaw-specific path or payload markers
///
/// Uses path hints first for formats that share the same pi session envelope
/// (generic pi sessions and OpenClaw SDK sessions both start with
/// `type:"session"`). Falls back to first-line content detection when the path
/// is uninformative.
pub fn detect_format(path: &Path) -> Option<SourceTool> {
    // Path hints are decisive for formats with shared JSONL envelopes.
    if let Some(tool) = detect_from_path(path) {
        return Some(tool);
    }

    // Try first-line content detection.
    if let Some(tool) = detect_from_first_line(path) {
        return Some(tool);
    }

    None
}

/// Auto-detect the format of a session log file and parse it.
///
/// Uses the cheap `detect_format` function (reads only the first line) to
/// identify the source tool, then dispatches to the matching parser's `parse`
/// method. This avoids a double-read: `can_parse` + `parse` would each read
/// the file independently.
pub fn parse_auto(path: &Path) -> Result<Vec<Session>> {
    // Skip empty files silently — Claude Code creates placeholder .jsonl files
    // for sessions that were opened but never had content written to them.
    if path.metadata().map(|m| m.len() == 0).unwrap_or(false) {
        return Ok(vec![]);
    }

    let parsers = all_parsers();

    let mut sessions = None;

    // Detect format cheaply (first line + path heuristics).
    if let Some(tool) = detect_format(path) {
        for parser in &parsers {
            if parser.source_tool() == tool {
                sessions =
                    Some(parser.parse(path).with_context(|| {
                        format!("{} parser failed on {}", tool, path.display())
                    })?);
                break;
            }
        }
    }

    // No format detected — try each parser's `can_parse` as a last resort.
    if sessions.is_none() {
        for parser in &parsers {
            if parser.can_parse(path) {
                sessions = Some(parser.parse(path).with_context(|| {
                    format!(
                        "{} parser failed on {}",
                        parser.source_tool(),
                        path.display()
                    )
                })?);
                break;
            }
        }
    }

    match sessions {
        Some(mut sessions) => {
            // Post-parsing: classify messages and refine session type.
            classify_sessions(&mut sessions);
            Ok(sessions)
        }
        None => {
            // No parser matched — return empty rather than erroring, so bulk
            // operations can continue with other files.
            eprintln!(
                "middens: no parser matched for {}, skipping",
                path.display()
            );
            Ok(vec![])
        }
    }
}

/// Classify all messages in each session, then refine the session type
/// based on the classifier's determination.
fn classify_sessions(sessions: &mut [Session]) {
    use crate::session::MessageRole;

    for session in sessions.iter_mut() {
        // Track whether this is the first user message (for positional classification).
        let mut first_user_seen = false;

        for msg in &mut session.messages {
            let is_first = if msg.role == MessageRole::User && !first_user_seen {
                first_user_seen = true;
                true
            } else {
                false
            };
            msg.classification = classify_message(msg, is_first);
        }

        // Override the parser's initial session_type guess with the classifier's
        // determination, which uses the now-classified messages.
        session.session_type = classify_session(session);
    }
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
            if model.starts_with("gpt")
                || model.starts_with("o1")
                || model.starts_with("o3")
                || model.starts_with("o4")
                || model.contains("codex")
            {
                return Some(SourceTool::CodexCli);
            }
        }
    }

    // Gemini CLI signals.
    if obj.contains_key("gemini") || obj.contains_key("generationConfig") {
        return Some(SourceTool::GeminiCli);
    }

    // OpenClaw explicit payload markers. Generic `type:"session"` JSONL is the
    // pi session envelope; OpenClaw is selected by path hint unless a payload
    // carries an explicit OpenClaw marker.
    if obj.contains_key("openclaw") {
        return Some(SourceTool::OpenClaw);
    }

    // Pi Coding Agent session JSONL. These are the files produced under
    // ~/.pi/agent/sessions and published by pi-share-hf datasets.
    if obj.get("type").and_then(|v| v.as_str()) == Some("session")
        && obj.get("id").and_then(|v| v.as_str()).is_some()
        && obj.get("cwd").and_then(|v| v.as_str()).is_some()
        && obj.get("version").and_then(|v| v.as_u64()).is_some()
    {
        return Some(SourceTool::PiCodingAgent);
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
    } else if s.contains(".pi/agent/sessions") {
        Some(SourceTool::PiCodingAgent)
    } else {
        None
    }
}
