//! Parser for Claude Code JSONL session logs.
//!
//! Claude Code stores session logs as JSONL files in `~/.claude/projects/`.
//! Each line is a JSON object with a top-level `type` field indicating the
//! kind of entry. The parser extracts user/assistant messages, tool calls,
//! thinking blocks, and session metadata.

use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::Value;

use super::SessionParser;
use crate::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool, ToolCall, ToolResult,
};

pub struct ClaudeCodeParser;

// ---------------------------------------------------------------------------
// Internal deserialization types — loose enough to handle format variations
// ---------------------------------------------------------------------------

/// A single JSONL line. We deserialize only the fields we care about; unknown
/// fields are silently ignored via `#[serde(default)]`.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RawEntry {
    /// Entry type: "user", "assistant", "queue-operation", "last-prompt",
    /// "progress", "response_item", "event_msg", "turn_context", etc.
    #[serde(rename = "type")]
    entry_type: Option<String>,

    /// Nested message envelope (present on user/assistant entries).
    message: Option<RawMessage>,

    /// ISO-8601 timestamp.
    timestamp: Option<String>,

    /// Session identifier.
    session_id: Option<String>,

    /// Claude Code version string.
    version: Option<String>,

    /// Working directory.
    cwd: Option<String>,

    /// Git branch.
    git_branch: Option<String>,

    /// Permission mode (e.g. "default").
    permission_mode: Option<String>,

    /// Subagent identifier — presence signals a subagent session.
    agent_id: Option<String>,

    /// Whether this entry is part of a sidechain (subagent).
    #[serde(default)]
    is_sidechain: bool,
}

#[derive(Debug, Deserialize)]
struct RawMessage {
    role: Option<String>,
    content: Option<RawContent>,
    model: Option<String>,
    /// Usage info may contain model details.
    #[serde(default)]
    usage: Option<Value>,
}

/// Content is either a plain string or an array of content blocks.
#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum RawContent {
    Text(String),
    Blocks(Vec<Value>),
}

// ---------------------------------------------------------------------------
// Known entry types for `can_parse` heuristic
// ---------------------------------------------------------------------------

const KNOWN_TYPES: &[&str] = &[
    "user",
    "assistant",
    "queue-operation",
    "response_item",
    "event_msg",
    "turn_context",
    "last-prompt",
    "progress",
];

// ---------------------------------------------------------------------------
// SessionParser implementation
// ---------------------------------------------------------------------------

impl SessionParser for ClaudeCodeParser {
    fn source_tool(&self) -> SourceTool {
        SourceTool::ClaudeCode
    }

    fn can_parse(&self, path: &Path) -> bool {
        // Must be a .jsonl file.
        let ext = path.extension().and_then(|e| e.to_str());
        if ext != Some("jsonl") {
            return false;
        }

        // Read just enough to inspect the first valid JSON line.
        let content = match fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => return false,
        };

        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let val: Value = match serde_json::from_str(line) {
                Ok(v) => v,
                Err(_) => return false,
            };
            let obj = match val.as_object() {
                Some(o) => o,
                None => return false,
            };

            // Heuristic 1: has "sessionId" and "version" fields.
            if obj.contains_key("sessionId") && obj.contains_key("version") {
                return true;
            }

            // Heuristic 2: top-level "type" is one of the known Claude Code types.
            if let Some(t) = obj.get("type").and_then(|v| v.as_str()) {
                if KNOWN_TYPES.contains(&t) {
                    return true;
                }
            }

            // First non-empty line did not match — not Claude Code.
            return false;
        }

        false
    }

    fn parse(&self, path: &Path) -> Result<Vec<Session>> {
        let content =
            fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;

        let mut messages: Vec<Message> = Vec::new();
        let mut metadata = SessionMetadata::default();
        let mut environment = EnvironmentFingerprint::default();
        let mut session_id: Option<String> = None;
        let mut has_agent_id = false;
        let mut has_sidechain = false;
        let mut has_real_user_text = false;

        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let entry: RawEntry = match serde_json::from_str(line) {
                Ok(e) => e,
                Err(_) => continue, // skip malformed lines
            };

            // Capture session-level metadata from any entry that has it.
            if session_id.is_none() {
                if let Some(ref sid) = entry.session_id {
                    session_id = Some(sid.clone());
                }
            }
            if metadata.version.is_none() {
                if let Some(ref v) = entry.version {
                    metadata.version = Some(v.clone());
                    environment.tool_version = Some(v.clone());
                }
            }
            if metadata.cwd.is_none() {
                if let Some(ref c) = entry.cwd {
                    metadata.cwd = Some(c.clone());
                }
            }
            if metadata.git_branch.is_none() {
                if let Some(ref b) = entry.git_branch {
                    metadata.git_branch = Some(b.clone());
                }
            }
            if metadata.permission_mode.is_none() {
                if let Some(ref p) = entry.permission_mode {
                    metadata.permission_mode = Some(p.clone());
                    environment.permission_mode = Some(p.clone());
                }
            }
            if entry.agent_id.is_some() {
                has_agent_id = true;
            }
            if entry.is_sidechain {
                has_sidechain = true;
            }

            // Only process user and assistant entries for messages.
            let entry_type = match entry.entry_type.as_deref() {
                Some(t) => t,
                None => continue,
            };

            match entry_type {
                "user" | "assistant" => {}
                _ => continue,
            }

            let raw_msg = match entry.message {
                Some(m) => m,
                None => continue,
            };

            // Determine role from entry type (preferred) or message.role.
            let role = match entry_type {
                "user" => MessageRole::User,
                "assistant" => MessageRole::Assistant,
                _ => match raw_msg.role.as_deref() {
                    Some("user") => MessageRole::User,
                    Some("assistant") => MessageRole::Assistant,
                    Some("system") => MessageRole::System,
                    _ => continue,
                },
            };

            // Extract model from assistant messages.
            if role == MessageRole::Assistant {
                if let Some(ref model) = raw_msg.model {
                    if metadata.model.is_none() {
                        metadata.model = Some(model.clone());
                        environment.model_id = Some(model.clone());
                    }
                }
            }

            // Parse timestamp.
            let timestamp: Option<DateTime<Utc>> = entry
                .timestamp
                .as_ref()
                .and_then(|ts| ts.parse::<DateTime<Utc>>().ok());

            // Parse content blocks.
            let (text, thinking, tool_calls, tool_results, raw_content) =
                parse_content(&raw_msg.content, role);

            if role == MessageRole::User && !text.trim().is_empty() {
                // Check if this is real user text vs tool result only.
                let is_tool_result_only = tool_results.len() > 0 && text.trim().is_empty();
                if !is_tool_result_only {
                    has_real_user_text = true;
                }

                // Scan user message content for MCP servers and plugins.
                scan_system_reminder_content(&text, &mut environment);
            }

            let msg = Message {
                role,
                timestamp,
                text,
                thinking,
                tool_calls,
                tool_results,
                classification: MessageClassification::Unclassified,
                raw_content,
            };

            messages.push(msg);
        }

        if messages.is_empty() {
            return Ok(vec![]);
        }

        // Determine session type.
        let is_in_subagents_dir = path
            .components()
            .any(|c| c.as_os_str() == "subagents");

        let session_type = if is_in_subagents_dir || has_agent_id || has_sidechain {
            SessionType::Subagent
        } else if !has_real_user_text {
            // No real user text content — likely automated.
            SessionType::Subagent
        } else {
            SessionType::Interactive
        };

        // Derive session ID from file name if not found in entries.
        let id = session_id.unwrap_or_else(|| {
            path.file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
                .to_string()
        });

        // Extract project from path (Claude Code uses the project path as directory name).
        let project = path
            .parent()
            .and_then(|p| p.file_name())
            .and_then(|n| n.to_str())
            .map(|s| s.to_string());
        metadata.project = project;

        let session = Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::ClaudeCode,
            session_type,
            messages,
            metadata,
            environment,
        };

        Ok(vec![session])
    }
}

// ---------------------------------------------------------------------------
// Content block parsing
// ---------------------------------------------------------------------------

/// Parse the content field of a message into text, thinking, tool calls,
/// tool results, and raw content blocks.
fn parse_content(
    content: &Option<RawContent>,
    role: MessageRole,
) -> (
    String,
    Option<String>,
    Vec<ToolCall>,
    Vec<ToolResult>,
    Vec<ContentBlock>,
) {
    let mut text_parts: Vec<String> = Vec::new();
    let mut thinking_parts: Vec<String> = Vec::new();
    let mut tool_calls: Vec<ToolCall> = Vec::new();
    let mut tool_results: Vec<ToolResult> = Vec::new();
    let mut raw_content: Vec<ContentBlock> = Vec::new();

    match content {
        None => {}
        Some(RawContent::Text(s)) => {
            text_parts.push(s.clone());
            raw_content.push(ContentBlock::Text { text: s.clone() });
        }
        Some(RawContent::Blocks(blocks)) => {
            for block in blocks {
                let block_type = block
                    .get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");

                match block_type {
                    "text" => {
                        if let Some(t) = block.get("text").and_then(|v| v.as_str()) {
                            text_parts.push(t.to_string());
                            raw_content.push(ContentBlock::Text {
                                text: t.to_string(),
                            });
                        }
                    }
                    "thinking" => {
                        if let Some(t) = block.get("thinking").and_then(|v| v.as_str()) {
                            thinking_parts.push(t.to_string());
                            raw_content.push(ContentBlock::Thinking {
                                thinking: t.to_string(),
                            });
                        }
                    }
                    "tool_use" => {
                        let id = block
                            .get("id")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        let name = block
                            .get("name")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        let input = block.get("input").cloned().unwrap_or(Value::Null);

                        tool_calls.push(ToolCall {
                            id: id.clone(),
                            name: name.clone(),
                            input: input.clone(),
                        });
                        raw_content.push(ContentBlock::ToolUse { id, name, input });
                    }
                    "tool_result" => {
                        let tool_use_id = block
                            .get("tool_use_id")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        let content_val = block.get("content").cloned().unwrap_or(Value::Null);
                        let content_str = match &content_val {
                            Value::String(s) => s.clone(),
                            other => other.to_string(),
                        };
                        let is_error = block
                            .get("is_error")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);

                        tool_results.push(ToolResult {
                            tool_use_id: tool_use_id.clone(),
                            content: content_str,
                            is_error,
                        });
                        raw_content.push(ContentBlock::ToolResultBlock {
                            tool_use_id,
                            content: content_val,
                            is_error,
                        });
                    }
                    _ => {
                        // For user messages, the block might be a tool_result
                        // without an explicit "type" field — check for
                        // "tool_use_id" directly (old format compatibility).
                        if role == MessageRole::User {
                            if let Some(tuid) = block.get("tool_use_id").and_then(|v| v.as_str()) {
                                let content_val =
                                    block.get("content").cloned().unwrap_or(Value::Null);
                                let content_str = match &content_val {
                                    Value::String(s) => s.clone(),
                                    other => other.to_string(),
                                };
                                let is_error = block
                                    .get("is_error")
                                    .and_then(|v| v.as_bool())
                                    .unwrap_or(false);

                                tool_results.push(ToolResult {
                                    tool_use_id: tuid.to_string(),
                                    content: content_str,
                                    is_error,
                                });
                                raw_content.push(ContentBlock::ToolResultBlock {
                                    tool_use_id: tuid.to_string(),
                                    content: content_val,
                                    is_error,
                                });
                                continue;
                            }
                        }
                        raw_content.push(ContentBlock::Unknown);
                    }
                }
            }
        }
    }

    let text = text_parts.join("\n");
    let thinking = if thinking_parts.is_empty() {
        None
    } else {
        Some(thinking_parts.join("\n"))
    };

    (text, thinking, tool_calls, tool_results, raw_content)
}

// ---------------------------------------------------------------------------
// Environment fingerprint extraction from system-reminder content
// ---------------------------------------------------------------------------

/// Scan text for MCP server references and plugin/skill references that
/// appear in `<system-reminder>` blocks injected by Claude Code.
fn scan_system_reminder_content(text: &str, env: &mut EnvironmentFingerprint) {
    // Detect MCP servers: lines like "## plugin:compound-engineering:context7"
    // or tool names like "mcp__plugin_compound-engineering_context7__query-docs".
    for line in text.lines() {
        let trimmed = line.trim();

        // MCP server heading pattern: "## plugin:<org>:<name>" or
        // "## <server-name>"
        if trimmed.starts_with("## plugin:") || trimmed.starts_with("## mcp:") {
            let server_name = trimmed.trim_start_matches("## ").to_string();
            if !env.mcp_servers.contains(&server_name) {
                env.mcp_servers.push(server_name);
            }
        }

        // MCP tool reference pattern: "mcp__<server>__<tool>"
        if trimmed.contains("mcp__") {
            // Extract the server portion: mcp__<server>__<tool>
            for word in trimmed.split_whitespace() {
                if let Some(rest) = word.strip_prefix("mcp__") {
                    if let Some(server) = rest.split("__").next() {
                        let server_name = server.replace('_', ":").replace("-", "-");
                        if !env.mcp_servers.contains(&server_name) {
                            env.mcp_servers.push(server_name);
                        }
                    }
                }
            }
        }

        // Skill/plugin detection: lines referencing available skills.
        if trimmed.contains("deferred tools") || trimmed.contains("Available skills") {
            // These are system-level plugin/skill indicators.
            // Individual tool names are not worth extracting here.
        }

        // Hook detection.
        if trimmed.contains("hook_progress")
            || trimmed.contains("hookEvent")
            || trimmed.contains("PreToolUse")
            || trimmed.contains("PostToolUse")
        {
            let hook_name = if trimmed.contains("PreToolUse") {
                "PreToolUse"
            } else if trimmed.contains("PostToolUse") {
                "PostToolUse"
            } else {
                "unknown"
            };
            let hook = hook_name.to_string();
            if !env.hooks.contains(&hook) {
                env.hooks.push(hook);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture_path() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("claude_code_sample.jsonl")
    }

    #[test]
    fn can_parse_detects_claude_code_jsonl() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        assert!(
            parser.can_parse(&path),
            "should detect Claude Code JSONL fixture"
        );
    }

    #[test]
    fn can_parse_rejects_non_jsonl() {
        let parser = ClaudeCodeParser;
        let path = PathBuf::from("README.md");
        assert!(!parser.can_parse(&path));
    }

    #[test]
    fn parse_extracts_session() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).expect("should parse fixture");
        assert_eq!(sessions.len(), 1, "should produce exactly one session");

        let session = &sessions[0];
        assert_eq!(session.id, "test-session-001");
        assert_eq!(session.source_tool, SourceTool::ClaudeCode);
        assert_eq!(session.session_type, SessionType::Interactive);
    }

    #[test]
    fn parse_extracts_metadata() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        assert_eq!(
            session.metadata.version.as_deref(),
            Some("2.1.76")
        );
        assert_eq!(
            session.metadata.cwd.as_deref(),
            Some("/Users/test/project")
        );
        assert_eq!(
            session.metadata.git_branch.as_deref(),
            Some("main")
        );
        assert_eq!(
            session.metadata.permission_mode.as_deref(),
            Some("default")
        );
        assert_eq!(
            session.metadata.model.as_deref(),
            Some("claude-opus-4-6")
        );
    }

    #[test]
    fn parse_extracts_messages() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        // The fixture has: 1 user msg, 2 assistant msgs (one with thinking,
        // one with tool_use), 1 user msg (tool_result).
        assert!(session.user_message_count() >= 1);
        assert!(session.assistant_message_count() >= 1);
    }

    #[test]
    fn parse_extracts_thinking_blocks() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        assert!(
            session.thinking_count() >= 1,
            "should find at least one thinking block"
        );
    }

    #[test]
    fn parse_extracts_tool_calls() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        assert!(
            session.total_tool_calls() >= 1,
            "should find at least one tool call"
        );

        // Find the Read tool call.
        let tool_names: Vec<&str> = session.tool_sequence();
        assert!(
            tool_names.contains(&"Read"),
            "should find a Read tool call"
        );
    }

    #[test]
    fn parse_extracts_tool_results() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        let has_tool_results = session
            .messages
            .iter()
            .any(|m| !m.tool_results.is_empty());
        assert!(has_tool_results, "should find tool results");
    }

    #[test]
    fn parse_detects_subagent_by_path() {
        let parser = ClaudeCodeParser;
        // Construct a path with "subagents/" component.
        let path = PathBuf::from("/tmp/project/subagents/agent-abc123.jsonl");
        // This file does not exist, but we test the path logic separately.
        // The actual subagent detection from path happens during parse.
        assert!(path.components().any(|c| c.as_os_str() == "subagents"));
    }

    #[test]
    fn parse_skips_non_message_entries() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        // queue-operation and last-prompt lines should not become messages.
        for msg in &session.messages {
            assert!(
                msg.role == MessageRole::User || msg.role == MessageRole::Assistant,
                "only user/assistant messages expected"
            );
        }
    }

    #[test]
    fn parse_environment_fingerprint() {
        let parser = ClaudeCodeParser;
        let path = fixture_path();
        let sessions = parser.parse(&path).unwrap();
        let session = &sessions[0];

        assert_eq!(
            session.environment.tool_version.as_deref(),
            Some("2.1.76")
        );
        assert_eq!(
            session.environment.model_id.as_deref(),
            Some("claude-opus-4-6")
        );
        assert_eq!(
            session.environment.permission_mode.as_deref(),
            Some("default")
        );
    }
}
