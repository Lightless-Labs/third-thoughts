use std::io::BufRead;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};

use super::SessionParser;
use crate::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole,
    ReasoningObservability, Session, SessionMetadata, SessionReasoningObservability, SessionType,
    SourceTool, ThinkingVisibility, ToolCall, ToolResult,
};

pub struct PiParser;

fn merge_reasoning_observability(
    current: ReasoningObservability,
    next: ReasoningObservability,
) -> ReasoningObservability {
    use ReasoningObservability::{Absent, FullTextVisible, SignatureOnly, SummaryVisible, Unknown};

    match (current, next) {
        (Unknown, _) | (_, Unknown) => Unknown,
        (FullTextVisible, _) | (_, FullTextVisible) => FullTextVisible,
        (SummaryVisible, _) | (_, SummaryVisible) => SummaryVisible,
        (SignatureOnly, _) | (_, SignatureOnly) => SignatureOnly,
        (Absent, Absent) => Absent,
    }
}

fn line_type(value: &serde_json::Value) -> Option<&str> {
    value.get("type").and_then(|v| v.as_str())
}

fn string_field(value: &serde_json::Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned)
}

fn is_pi_session_header(value: &serde_json::Value) -> bool {
    line_type(value) == Some("session")
        && value.get("id").and_then(|v| v.as_str()).is_some()
        && value.get("cwd").and_then(|v| v.as_str()).is_some()
        && value.get("version").and_then(|v| v.as_u64()).is_some()
}

fn text_from_content(content: &serde_json::Value) -> String {
    match content {
        serde_json::Value::String(text) => text.clone(),
        serde_json::Value::Array(blocks) => blocks
            .iter()
            .filter_map(|block| block.get("text").and_then(|v| v.as_str()))
            .collect::<Vec<_>>()
            .join("\n"),
        serde_json::Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn timestamp_from_entry(value: &serde_json::Value) -> Option<DateTime<Utc>> {
    value
        .get("timestamp")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<DateTime<Utc>>().ok())
}

impl SessionParser for PiParser {
    fn source_tool(&self) -> SourceTool {
        SourceTool::PiCodingAgent
    }

    fn can_parse(&self, path: &Path) -> bool {
        if path.extension().and_then(|e| e.to_str()) != Some("jsonl") {
            return false;
        }

        if let Some(path_str) = path.to_str() {
            if path_str.contains("openclaw") {
                return false;
            }
            if path_str.contains(".pi/agent/sessions") {
                return true;
            }
        }

        let Ok(file) = std::fs::File::open(path) else {
            return false;
        };
        let reader = std::io::BufReader::new(file);
        let Some(Ok(first_line)) = reader.lines().next() else {
            return false;
        };
        let Ok(value) = serde_json::from_str::<serde_json::Value>(&first_line) else {
            return false;
        };

        is_pi_session_header(&value)
    }

    fn parse(&self, path: &Path) -> Result<Vec<Session>> {
        let file =
            std::fs::File::open(path).with_context(|| format!("opening {}", path.display()))?;
        let reader = std::io::BufReader::new(file);

        let mut session_id: Option<String> = None;
        let mut metadata = SessionMetadata::default();
        let mut environment = EnvironmentFingerprint::default();
        let mut messages: Vec<Message> = Vec::new();

        let mut current_provider: Option<String> = None;
        let mut current_model: Option<String> = None;
        let mut thinking_level: Option<String> = None;

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

            let parsed: serde_json::Value = match serde_json::from_str(&line) {
                Ok(p) => p,
                Err(_) => continue,
            };

            match line_type(&parsed) {
                Some("session") => {
                    session_id = string_field(&parsed, "id");
                    metadata.cwd = string_field(&parsed, "cwd");
                    if let Some(version) = parsed.get("version").and_then(|v| v.as_u64()) {
                        metadata.extra.insert(
                            "format_version".into(),
                            serde_json::Value::Number(version.into()),
                        );
                    }
                    if let Some(parent) = parsed.get("parentSession").cloned() {
                        metadata.extra.insert("parent_session".into(), parent);
                    }
                }

                Some("model_change") => {
                    current_provider = string_field(&parsed, "provider").or(current_provider);
                    current_model = string_field(&parsed, "modelId").or(current_model);
                }

                Some("thinking_level_change") => {
                    thinking_level = string_field(&parsed, "thinkingLevel");
                }

                Some("custom") => {
                    if parsed.get("customType").and_then(|v| v.as_str()) == Some("model-snapshot") {
                        if let Some(data) = parsed.get("data") {
                            current_provider = string_field(data, "provider").or(current_provider);
                            current_model = string_field(data, "modelId").or(current_model);
                        }
                    }
                }

                Some("message") => {
                    let Some(msg) = parsed.get("message") else {
                        continue;
                    };
                    let role_str = msg.get("role").and_then(|v| v.as_str()).unwrap_or("");
                    let role = match role_str {
                        "user" => MessageRole::User,
                        "assistant" => MessageRole::Assistant,
                        "system" | "developer" => MessageRole::System,
                        // Pi stores tool results as first-class messages; middens keeps
                        // tool-result payloads on a message, so use System to prevent
                        // downstream user-correction classifiers from treating command
                        // output as human text.
                        "toolResult" | "bashExecution" | "custom" => MessageRole::System,
                        _ => MessageRole::System,
                    };

                    let ts = timestamp_from_entry(&parsed);
                    let content = msg.get("content").unwrap_or(&serde_json::Value::Null);

                    let mut text_parts: Vec<String> = Vec::new();
                    let mut thinking_parts: Vec<String> = Vec::new();
                    let mut reasoning_observability = ReasoningObservability::Absent;
                    let mut tool_calls: Vec<ToolCall> = Vec::new();
                    let mut tool_results: Vec<ToolResult> = Vec::new();
                    let mut raw_content: Vec<ContentBlock> = Vec::new();

                    if role_str == "toolResult" {
                        let tool_call_id = string_field(msg, "toolCallId").unwrap_or_default();
                        let text = text_from_content(content);
                        let is_error = msg
                            .get("isError")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);
                        tool_results.push(ToolResult {
                            tool_use_id: tool_call_id.clone(),
                            content: text.clone(),
                            is_error,
                        });
                        raw_content.push(ContentBlock::ToolResultBlock {
                            tool_use_id: tool_call_id,
                            content: content.clone(),
                            is_error,
                        });
                        text_parts.push(text);
                    } else if role_str == "bashExecution" {
                        let command = string_field(msg, "command").unwrap_or_default();
                        let output = string_field(msg, "output").unwrap_or_default();
                        let text = if command.is_empty() {
                            output
                        } else {
                            format!("$ {command}\n{output}")
                        };
                        text_parts.push(text.clone());
                        raw_content.push(ContentBlock::Text { text });
                    } else {
                        match content {
                            serde_json::Value::String(text) => {
                                text_parts.push(text.clone());
                                raw_content.push(ContentBlock::Text { text: text.clone() });
                            }
                            serde_json::Value::Array(blocks) => {
                                for block in blocks {
                                    match block.get("type").and_then(|v| v.as_str()) {
                                        Some("text") => {
                                            let text =
                                                string_field(block, "text").unwrap_or_default();
                                            text_parts.push(text.clone());
                                            raw_content.push(ContentBlock::Text { text });
                                        }
                                        Some("thinking") => {
                                            let thinking =
                                                string_field(block, "thinking").unwrap_or_default();
                                            let redacted = block
                                                .get("redacted")
                                                .and_then(|v| v.as_bool())
                                                .unwrap_or(false);
                                            let has_signature = block
                                                .get("thinkingSignature")
                                                .and_then(|v| v.as_str())
                                                .is_some();

                                            if !thinking.trim().is_empty() && !redacted {
                                                thinking_parts.push(thinking.clone());
                                                reasoning_observability =
                                                    merge_reasoning_observability(
                                                        reasoning_observability,
                                                        ReasoningObservability::FullTextVisible,
                                                    );
                                                raw_content
                                                    .push(ContentBlock::Thinking { thinking });
                                            } else if has_signature {
                                                reasoning_observability =
                                                    merge_reasoning_observability(
                                                        reasoning_observability,
                                                        ReasoningObservability::SignatureOnly,
                                                    );
                                                raw_content.push(ContentBlock::ReasoningSignature);
                                            }
                                        }
                                        Some("toolCall") => {
                                            let id = string_field(block, "id").unwrap_or_default();
                                            let name =
                                                string_field(block, "name").unwrap_or_default();
                                            let input = block
                                                .get("arguments")
                                                .cloned()
                                                .unwrap_or(serde_json::Value::Null);
                                            tool_calls.push(ToolCall {
                                                id: id.clone(),
                                                name: name.clone(),
                                                input: input.clone(),
                                            });
                                            raw_content.push(ContentBlock::ToolUse {
                                                id,
                                                name,
                                                input,
                                            });
                                        }
                                        Some(_) | None => raw_content.push(ContentBlock::Unknown),
                                    }
                                }
                            }
                            serde_json::Value::Null => {}
                            other => {
                                let text = other.to_string();
                                text_parts.push(text.clone());
                                raw_content.push(ContentBlock::Text { text });
                            }
                        }
                    }

                    if role == MessageRole::Assistant {
                        current_provider = string_field(msg, "provider").or(current_provider);
                        current_model = string_field(msg, "model").or(current_model);
                    }

                    let thinking = if thinking_parts.is_empty() {
                        None
                    } else {
                        Some(thinking_parts.join("\n"))
                    };

                    messages.push(Message {
                        role,
                        timestamp: ts,
                        text: text_parts.join("\n"),
                        thinking,
                        reasoning_summary: None,
                        reasoning_observability,
                        tool_calls,
                        tool_results,
                        classification: MessageClassification::Unclassified,
                        raw_content,
                    });
                }

                Some("compaction") | Some("branch_summary") => {
                    if let Some(summary) = string_field(&parsed, "summary") {
                        messages.push(Message {
                            role: MessageRole::System,
                            timestamp: timestamp_from_entry(&parsed),
                            text: summary.clone(),
                            thinking: None,
                            reasoning_summary: None,
                            reasoning_observability: ReasoningObservability::Absent,
                            tool_calls: vec![],
                            tool_results: vec![],
                            classification: MessageClassification::Unclassified,
                            raw_content: vec![ContentBlock::Text { text: summary }],
                        });
                    }
                }

                _ => {}
            }
        }

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

        let id = session_id.unwrap_or_else(|| {
            path.file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
                .to_string()
        });

        let session_type = if messages.iter().any(|m| m.role == MessageRole::User) {
            SessionType::Interactive
        } else {
            SessionType::Unknown
        };
        let reasoning_observability = SessionReasoningObservability::from_messages(&messages);
        let thinking_visibility = if messages.iter().any(|m| m.thinking.is_some()) {
            ThinkingVisibility::Visible
        } else {
            ThinkingVisibility::Unknown
        };

        Ok(vec![Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::PiCodingAgent,
            session_type,
            messages,
            metadata,
            environment,
            thinking_visibility,
            reasoning_observability,
        }])
    }
}
