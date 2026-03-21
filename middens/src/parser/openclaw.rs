use std::io::BufRead;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::Deserialize;

use super::SessionParser;
use crate::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool, ToolCall, ToolResult,
};

pub struct OpenClawParser;

// ---------------------------------------------------------------------------
// Raw deserialization types mirroring OpenClaw JSONL structure
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct OpenClawLine {
    #[serde(rename = "type")]
    line_type: String,
    #[serde(default)]
    id: Option<String>,
    #[serde(default)]
    timestamp: Option<String>,
    #[serde(default)]
    version: Option<u32>,
    #[serde(default)]
    cwd: Option<String>,

    // model_change fields
    #[serde(default)]
    provider: Option<String>,
    #[serde(default, rename = "modelId")]
    model_id: Option<String>,

    // thinking_level_change fields
    #[serde(default, rename = "thinkingLevel")]
    thinking_level: Option<String>,

    // message fields
    #[serde(default)]
    message: Option<OpenClawMessage>,

    // custom fields
    #[serde(default, rename = "customType")]
    custom_type: Option<String>,
    #[serde(default)]
    data: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct OpenClawMessage {
    role: String,
    #[serde(default)]
    content: Vec<OpenClawContentBlock>,
    #[serde(default)]
    timestamp: Option<serde_json::Value>,

    // Response metadata (present on assistant messages).
    #[serde(default)]
    api: Option<String>,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    usage: Option<UsageInfo>,
    #[serde(default, rename = "stopReason")]
    stop_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct UsageInfo {
    #[serde(default)]
    input: Option<u64>,
    #[serde(default)]
    output: Option<u64>,
    #[serde(default, rename = "cacheRead")]
    cache_read: Option<u64>,
    #[serde(default, rename = "totalTokens")]
    total_tokens: Option<u64>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum OpenClawContentBlock {
    #[serde(rename = "text")]
    Text {
        text: String,
        #[serde(default, rename = "textSignature")]
        #[allow(dead_code)]
        text_signature: Option<String>,
    },
    #[serde(rename = "thinking")]
    Thinking {
        thinking: String,
    },
    #[serde(rename = "tool_use")]
    ToolUse {
        #[serde(default)]
        id: String,
        #[serde(default)]
        name: String,
        #[serde(default)]
        input: serde_json::Value,
    },
    #[serde(rename = "tool_result")]
    ToolResultBlock {
        #[serde(default)]
        tool_use_id: String,
        #[serde(default)]
        content: serde_json::Value,
        #[serde(default)]
        is_error: bool,
    },
    #[serde(other)]
    Unknown,
}

// ---------------------------------------------------------------------------
// Multi-agent metadata extraction
// ---------------------------------------------------------------------------

/// Try to extract the agent name from the OpenClaw session file path.
/// Per-agent files are named like `albert-spangler.jsonl`.
fn agent_name_from_path(path: &Path) -> Option<String> {
    let stem = path.file_stem()?.to_str()?;
    if stem == "main" {
        None // The main orchestrator file has no specific agent name.
    } else {
        Some(stem.to_string())
    }
}

/// Try to extract sender metadata from the first user message content.
/// OpenClaw embeds JSON blocks like:
/// ```text
/// Sender (untrusted metadata):
/// ```json
/// { "label": "Thomas", "name": "Thomas", ... }
/// ```
/// ```
fn extract_sender_info(text: &str) -> Option<serde_json::Value> {
    let marker = "Sender (untrusted metadata):";
    let idx = text.find(marker)?;
    let after = &text[idx + marker.len()..];
    // Find the JSON block between ```json and ```.
    let json_start = after.find("```json\n").or_else(|| after.find("```json\r\n"))?;
    let json_body = &after[json_start + 8..]; // skip "```json\n"
    let json_end = json_body.find("```")?;
    let json_str = json_body[..json_end].trim();
    serde_json::from_str(json_str).ok()
}

/// Try to extract conversation label from the first user message content.
fn extract_conversation_label(text: &str) -> Option<String> {
    let marker = "Conversation info (untrusted metadata):";
    let idx = text.find(marker)?;
    let after = &text[idx + marker.len()..];
    let json_start = after.find("```json\n").or_else(|| after.find("```json\r\n"))?;
    let json_body = &after[json_start + 8..];
    let json_end = json_body.find("```")?;
    let json_str = json_body[..json_end].trim();
    let parsed: serde_json::Value = serde_json::from_str(json_str).ok()?;
    parsed
        .get("conversation_label")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

impl SessionParser for OpenClawParser {
    fn source_tool(&self) -> SourceTool {
        SourceTool::OpenClaw
    }

    fn can_parse(&self, path: &Path) -> bool {
        let ext = path.extension().and_then(|e| e.to_str());
        if ext != Some("jsonl") {
            return false;
        }

        // Check if the directory name hints at openclaw.
        if let Some(path_str) = path.to_str() {
            if path_str.contains("openclaw") {
                return true;
            }
        }

        // Peek at the first line: OpenClaw starts with type:"session" + version field.
        if let Ok(file) = std::fs::File::open(path) {
            let reader = std::io::BufReader::new(file);
            if let Some(Ok(first_line)) = reader.lines().next() {
                if let Ok(line) = serde_json::from_str::<OpenClawLine>(&first_line) {
                    return line.line_type == "session" && line.version.is_some();
                }
            }
        }
        false
    }

    fn parse(&self, path: &Path) -> Result<Vec<Session>> {
        let file =
            std::fs::File::open(path).with_context(|| format!("opening {}", path.display()))?;
        let reader = std::io::BufReader::new(file);

        let mut session_id: Option<String> = None;
        let mut metadata = SessionMetadata::default();
        let mut environment = EnvironmentFingerprint::default();
        let mut messages: Vec<Message> = Vec::new();

        // Track provider / model across model_change lines.
        let mut current_provider: Option<String> = None;
        let mut current_model: Option<String> = None;
        let mut thinking_level: Option<String> = None;

        // Multi-agent metadata.
        let agent_name = agent_name_from_path(path);
        let mut conversation_label: Option<String> = None;
        let mut first_user_seen = false;

        for line_result in reader.lines() {
            let line = match line_result {
                Ok(l) if !l.trim().is_empty() => l,
                Ok(_) => continue,
                Err(e) => {
                    eprintln!(
                        "warning: skipping unreadable line in {}: {e}",
                        path.display()
                    );
                    continue;
                }
            };

            let parsed: OpenClawLine = match serde_json::from_str(&line) {
                Ok(p) => p,
                Err(_) => continue,
            };

            match parsed.line_type.as_str() {
                "session" => {
                    session_id = parsed.id.clone();
                    if let Some(cwd) = parsed.cwd {
                        metadata.cwd = Some(cwd);
                    }
                    if let Some(v) = parsed.version {
                        metadata
                            .extra
                            .insert("format_version".into(), serde_json::Value::Number(v.into()));
                    }
                }

                "model_change" => {
                    if let Some(provider) = parsed.provider {
                        current_provider = Some(provider);
                    }
                    if let Some(model) = parsed.model_id {
                        current_model = Some(model);
                    }
                }

                "thinking_level_change" => {
                    thinking_level = parsed.thinking_level;
                }

                "custom" => {
                    // model-snapshot custom events carry provider/model too.
                    if parsed.custom_type.as_deref() == Some("model-snapshot") {
                        if let Some(data) = &parsed.data {
                            if let Some(model) = data.get("modelId").and_then(|v| v.as_str()) {
                                current_model = Some(model.to_string());
                            }
                            if let Some(provider) = data.get("provider").and_then(|v| v.as_str()) {
                                current_provider = Some(provider.to_string());
                            }
                        }
                    }
                }

                "message" => {
                    if let Some(msg) = parsed.message {
                        let role = match msg.role.as_str() {
                            "user" => MessageRole::User,
                            "assistant" => MessageRole::Assistant,
                            "system" | "developer" => MessageRole::System,
                            _ => MessageRole::System,
                        };

                        // Parse timestamp from either the line-level or message-level field.
                        let ts = parsed
                            .timestamp
                            .as_deref()
                            .and_then(|s| s.parse::<DateTime<Utc>>().ok());

                        let mut text_parts: Vec<String> = Vec::new();
                        let mut thinking_parts: Vec<String> = Vec::new();
                        let mut tool_calls: Vec<ToolCall> = Vec::new();
                        let mut tool_results: Vec<ToolResult> = Vec::new();
                        let mut raw_content: Vec<ContentBlock> = Vec::new();

                        for block in &msg.content {
                            match block {
                                OpenClawContentBlock::Text { text, .. } => {
                                    text_parts.push(text.clone());
                                    raw_content.push(ContentBlock::Text { text: text.clone() });
                                }
                                OpenClawContentBlock::Thinking { thinking } => {
                                    thinking_parts.push(thinking.clone());
                                    raw_content.push(ContentBlock::Thinking {
                                        thinking: thinking.clone(),
                                    });
                                }
                                OpenClawContentBlock::ToolUse { id, name, input } => {
                                    tool_calls.push(ToolCall {
                                        id: id.clone(),
                                        name: name.clone(),
                                        input: input.clone(),
                                    });
                                    raw_content.push(ContentBlock::ToolUse {
                                        id: id.clone(),
                                        name: name.clone(),
                                        input: input.clone(),
                                    });
                                }
                                OpenClawContentBlock::ToolResultBlock {
                                    tool_use_id,
                                    content,
                                    is_error,
                                } => {
                                    let content_str = match content {
                                        serde_json::Value::String(s) => s.clone(),
                                        other => other.to_string(),
                                    };
                                    tool_results.push(ToolResult {
                                        tool_use_id: tool_use_id.clone(),
                                        content: content_str.clone(),
                                        is_error: *is_error,
                                    });
                                    raw_content.push(ContentBlock::ToolResultBlock {
                                        tool_use_id: tool_use_id.clone(),
                                        content: content.clone(),
                                        is_error: *is_error,
                                    });
                                }
                                OpenClawContentBlock::Unknown => {
                                    raw_content.push(ContentBlock::Unknown);
                                }
                            }
                        }

                        let text = text_parts.join("\n");
                        let thinking = if thinking_parts.is_empty() {
                            None
                        } else {
                            Some(thinking_parts.join("\n"))
                        };

                        // Extract multi-agent metadata from first user message.
                        if role == MessageRole::User && !first_user_seen {
                            first_user_seen = true;
                            if let Some(label) = extract_conversation_label(&text) {
                                conversation_label = Some(label);
                            }
                            if let Some(sender) = extract_sender_info(&text) {
                                metadata.extra.insert("first_sender".into(), sender);
                            }
                        }

                        // Capture per-message model/provider if present on assistant messages.
                        if role == MessageRole::Assistant {
                            if let Some(model) = &msg.model {
                                if current_model.as_deref() != Some(model) {
                                    current_model = Some(model.clone());
                                }
                            }
                            if let Some(provider) = &msg.provider {
                                if current_provider.as_deref() != Some(provider) {
                                    current_provider = Some(provider.clone());
                                }
                            }
                            // Track if this message was delivered via the openclaw mirror.
                            if msg.api.as_deref() == Some("openai-responses")
                                && msg.provider.as_deref() == Some("openclaw")
                                && msg.model.as_deref() == Some("delivery-mirror")
                            {
                                metadata.extra.insert(
                                    "uses_delivery_mirror".into(),
                                    serde_json::Value::Bool(true),
                                );
                            }
                        }

                        messages.push(Message {
                            role,
                            timestamp: ts,
                            text,
                            thinking,
                            tool_calls,
                            tool_results,
                            classification: MessageClassification::Unclassified,
                            raw_content,
                        });
                    }
                }

                _ => {}
            }
        }

        // Fill metadata from accumulated state.
        if let Some(model) = &current_model {
            metadata.model = Some(model.clone());
            environment.model_id = Some(model.clone());
        }
        if let Some(provider) = &current_provider {
            metadata.extra.insert(
                "provider".into(),
                serde_json::Value::String(provider.clone()),
            );
        }
        if let Some(level) = &thinking_level {
            metadata.extra.insert(
                "thinking_level".into(),
                serde_json::Value::String(level.clone()),
            );
        }
        if let Some(name) = &agent_name {
            metadata.extra.insert(
                "agent_name".into(),
                serde_json::Value::String(name.clone()),
            );
        }
        if let Some(label) = &conversation_label {
            metadata.extra.insert(
                "conversation_label".into(),
                serde_json::Value::String(label.clone()),
            );
        }

        let id = session_id.unwrap_or_else(|| {
            path.file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
                .to_string()
        });

        // OpenClaw sessions with agent names are automated sub-agents.
        // The "main" session is the orchestrator and may be interactive.
        let session_type = if agent_name.is_some() {
            SessionType::Subagent
        } else if messages.iter().any(|m| m.role == MessageRole::User) {
            SessionType::Interactive
        } else {
            SessionType::Unknown
        };

        let session = Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::OpenClaw,
            session_type,
            messages,
            metadata,
            environment,
        };

        Ok(vec![session])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn can_parse_detects_openclaw_fixture() {
        let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/openclaw_sample.jsonl");
        if fixture.exists() {
            let parser = OpenClawParser;
            assert!(parser.can_parse(&fixture));
        }
    }

    #[test]
    fn parse_openclaw_fixture() {
        let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/openclaw_sample.jsonl");
        if !fixture.exists() {
            return;
        }
        let parser = OpenClawParser;
        let sessions = parser.parse(&fixture).expect("parse should succeed");
        assert_eq!(sessions.len(), 1);

        let s = &sessions[0];
        assert_eq!(s.source_tool, SourceTool::OpenClaw);
        assert_eq!(s.id, "test-openclaw-session-001");
        assert_eq!(
            s.metadata.cwd.as_deref(),
            Some("/tmp/openclaw-workspace")
        );
        assert!(s.metadata.model.is_some());

        // Should have user + assistant messages.
        assert!(s.user_message_count() >= 1);
        assert!(s.assistant_message_count() >= 1);

        // Multi-agent metadata should be extracted.
        assert!(s.metadata.extra.contains_key("provider"));
    }

    #[test]
    fn agent_name_extraction() {
        assert_eq!(
            agent_name_from_path(Path::new("/tmp/sessions/albert-spangler.jsonl")),
            Some("albert-spangler".to_string())
        );
        assert_eq!(
            agent_name_from_path(Path::new("/tmp/sessions/main.jsonl")),
            None
        );
    }

    #[test]
    fn rejects_non_openclaw_file() {
        let parser = OpenClawParser;
        assert!(!parser.can_parse(Path::new("/tmp/random.jsonl")));
        assert!(!parser.can_parse(Path::new("/tmp/file.json")));
    }
}
