//! Parser for Claude Code JSONL session logs.
//!
//! Claude Code stores session logs as JSONL files in `~/.claude/projects/`.
//! Each line is a JSON object with a top-level `type` field indicating the
//! kind of entry. The parser extracts user/assistant messages, tool calls,
//! thinking blocks, and session metadata.

use std::fs;
use std::io::BufRead;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::Value;

use super::SessionParser;
use crate::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool, ThinkingVisibility, ToolCall, ToolResult,
};

/// Cutoff timestamp for the `redact-thinking-2026-02-12` beta header rollout.
/// Sessions starting on/after this instant with no thinking blocks are
/// assumed to have been captured under the redacted default.
const REDACT_THINKING_CUTOFF: &str = "2026-02-12T00:00:00Z";

/// Parse the cutoff once and reuse across `parse` calls.
fn redact_thinking_cutoff() -> &'static DateTime<Utc> {
    use std::sync::OnceLock;
    static CUTOFF: OnceLock<DateTime<Utc>> = OnceLock::new();
    CUTOFF.get_or_init(|| {
        REDACT_THINKING_CUTOFF
            .parse()
            .expect("REDACT_THINKING_CUTOFF must be a valid RFC 3339 timestamp")
    })
}

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

        // Read only the first line using BufReader — avoid loading the entire file.
        let file = match fs::File::open(path) {
            Ok(f) => f,
            Err(_) => return false,
        };
        let reader = std::io::BufReader::new(file);

        for line in reader.lines() {
            let line = match line {
                Ok(l) => l,
                Err(_) => return false,
            };
            let line = line.trim().to_string();
            if line.is_empty() {
                continue;
            }

            let val: Value = match serde_json::from_str(&line) {
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

            if role == MessageRole::User {
                // Check if this message consists solely of tool_result blocks
                // with no human-typed text. Such messages should NOT count as
                // real user text — they are automated tool result returns.
                let is_tool_result_only = !tool_results.is_empty() && text.trim().is_empty();
                if !is_tool_result_only && !text.trim().is_empty() {
                    has_real_user_text = true;
                }

                // Scan user message content for MCP servers and plugins.
                if !text.trim().is_empty() {
                    scan_system_reminder_content(&text, &mut environment);
                }
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
        let is_in_subagents_dir = path.components().any(|c| c.as_os_str() == "subagents");

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

        // Derive thinking_visibility heuristic.
        //
        // Limitations: we cannot read HTTP headers from a stored transcript,
        // so this is a best-effort inference. A session could in principle
        // be post-cutoff but have the beta header disabled (→ Visible) or
        // be pre-cutoff yet have zero thinking for unrelated reasons (→
        // misclassified Visible — conservative, keeps the session in the
        // analysis). The Unknown bucket captures sessions with no usable
        // timestamps.
        let mut any_thinking = false;
        let mut earliest_ts: Option<DateTime<Utc>> = None;
        for m in &messages {
            if m.thinking.is_some() {
                any_thinking = true;
            }
            if let Some(ts) = m.timestamp {
                if earliest_ts.map_or(true, |e| ts < e) {
                    earliest_ts = Some(ts);
                }
            }
        }
        let cutoff: DateTime<Utc> = *redact_thinking_cutoff();
        let thinking_visibility = if any_thinking {
            ThinkingVisibility::Visible
        } else {
            match earliest_ts {
                Some(ts) if ts < cutoff => ThinkingVisibility::Visible,
                Some(_) => ThinkingVisibility::Redacted,
                None => ThinkingVisibility::Unknown,
            }
        };

        let session = Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::ClaudeCode,
            session_type,
            messages,
            metadata,
            environment,
            thinking_visibility,
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
                let block_type = block.get("type").and_then(|v| v.as_str()).unwrap_or("");

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
