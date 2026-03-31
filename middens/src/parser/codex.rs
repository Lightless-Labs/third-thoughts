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

pub struct CodexParser;

// ---------------------------------------------------------------------------
// Raw deserialization types mirroring Codex CLI JSONL structure
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct CodexLine {
    timestamp: Option<String>,
    #[serde(rename = "type")]
    line_type: String,
    #[serde(default)]
    payload: serde_json::Value,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct SessionMetaPayload {
    id: Option<String>,
    #[serde(default)]
    timestamp: Option<String>,
    cwd: Option<String>,
    cli_version: Option<String>,
    model_provider: Option<String>,
    #[serde(default)]
    base_instructions: Option<serde_json::Value>,
    #[serde(default)]
    git: Option<GitInfo>,
}

#[derive(Debug, Deserialize)]
struct GitInfo {
    #[serde(default)]
    branch: Option<String>,
    #[serde(default)]
    commit_hash: Option<String>,
    #[serde(default)]
    repository_url: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ResponseItemPayload {
    #[serde(rename = "type")]
    item_type: Option<String>,
    role: Option<String>,
    #[serde(default)]
    content: Vec<RawContentBlock>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum RawContentBlock {
    #[serde(rename = "input_text")]
    InputText {
        text: String,
    },
    #[serde(rename = "output_text")]
    OutputText {
        text: String,
    },
    #[serde(rename = "text")]
    Text {
        text: String,
    },
    #[serde(rename = "thinking")]
    Thinking {
        thinking: Option<String>,
        #[serde(default)]
        #[allow(dead_code)]
        summary: Option<serde_json::Value>,
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

#[derive(Debug, Deserialize)]
struct TurnContextPayload {
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    approval_policy: Option<String>,
    #[serde(default)]
    sandbox_policy: Option<serde_json::Value>,
    #[serde(default)]
    effort: Option<String>,
    #[serde(default)]
    personality: Option<String>,
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

impl SessionParser for CodexParser {
    fn source_tool(&self) -> SourceTool {
        SourceTool::CodexCli
    }

    fn can_parse(&self, path: &Path) -> bool {
        let ext = path.extension().and_then(|e| e.to_str());
        if ext != Some("jsonl") {
            return false;
        }

        // Check if it lives under a codex sessions directory or the first line
        // looks like a Codex session_meta entry.
        if let Some(path_str) = path.to_str() {
            if path_str.contains(".codex/sessions") {
                return true;
            }
        }

        // Peek at the first line.
        if let Ok(file) = std::fs::File::open(path) {
            let reader = std::io::BufReader::new(file);
            if let Some(Ok(first_line)) = reader.lines().next() {
                if let Ok(line) = serde_json::from_str::<CodexLine>(&first_line) {
                    return line.line_type == "session_meta";
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

        for line_result in reader.lines() {
            let line = match line_result {
                Ok(l) if !l.trim().is_empty() => l,
                Ok(_) => continue,
                Err(e) => {
                    // Skip lines that can't be read (encoding issues etc.)
                    eprintln!("warning: skipping unreadable line in {}: {e}", path.display());
                    continue;
                }
            };

            let parsed: CodexLine = match serde_json::from_str(&line) {
                Ok(p) => p,
                Err(_) => continue, // skip malformed lines
            };

            match parsed.line_type.as_str() {
                "session_meta" => {
                    if let Ok(meta) =
                        serde_json::from_value::<SessionMetaPayload>(parsed.payload.clone())
                    {
                        session_id = meta.id.clone();
                        metadata.cwd = meta.cwd;
                        metadata.version = meta.cli_version.clone();
                        environment.tool_version = meta.cli_version;

                        if let Some(provider) = meta.model_provider {
                            metadata
                                .extra
                                .insert("model_provider".into(), serde_json::Value::String(provider));
                        }

                        if let Some(git) = meta.git {
                            metadata.git_branch = git.branch;
                            if let Some(hash) = git.commit_hash {
                                metadata
                                    .extra
                                    .insert("git_commit".into(), serde_json::Value::String(hash));
                            }
                            if let Some(url) = git.repository_url {
                                metadata
                                    .extra
                                    .insert("git_repo".into(), serde_json::Value::String(url));
                            }
                        }

                        // session-level timestamp available in meta.timestamp
                        // if needed in the future.
                    }
                }

                "turn_context" => {
                    if let Ok(ctx) =
                        serde_json::from_value::<TurnContextPayload>(parsed.payload.clone())
                    {
                        if let Some(model) = ctx.model {
                            metadata.model = Some(model.clone());
                            environment.model_id = Some(model);
                        }
                        if let Some(policy) = ctx.approval_policy {
                            metadata.permission_mode = Some(policy.clone());
                            environment.permission_mode = Some(policy);
                        }
                        if let Some(effort) = ctx.effort {
                            metadata
                                .extra
                                .insert("effort".into(), serde_json::Value::String(effort));
                        }
                        if let Some(personality) = ctx.personality {
                            metadata
                                .extra
                                .insert("personality".into(), serde_json::Value::String(personality));
                        }
                        if let Some(sandbox) = ctx.sandbox_policy {
                            // Extract sandbox type.
                            if let Some(sb_type) = sandbox.get("type").and_then(|v| v.as_str()) {
                                metadata.extra.insert(
                                    "sandbox_policy".into(),
                                    serde_json::Value::String(sb_type.to_string()),
                                );
                            }
                        }
                    }
                }

                "response_item" => {
                    if let Ok(item) =
                        serde_json::from_value::<ResponseItemPayload>(parsed.payload.clone())
                    {
                        let item_type = item.item_type.as_deref().unwrap_or("");
                        if item_type == "message" {
                            let role = match item.role.as_deref() {
                                Some("user") => MessageRole::User,
                                Some("assistant") => MessageRole::Assistant,
                                Some("developer") | Some("system") => MessageRole::System,
                                _ => MessageRole::System,
                            };

                            let ts = parsed
                                .timestamp
                                .as_deref()
                                .and_then(|s| s.parse::<DateTime<Utc>>().ok());

                            let mut text_parts: Vec<String> = Vec::new();
                            let mut thinking_parts: Vec<String> = Vec::new();
                            let mut tool_calls: Vec<ToolCall> = Vec::new();
                            let mut tool_results: Vec<ToolResult> = Vec::new();
                            let mut raw_content: Vec<ContentBlock> = Vec::new();

                            for block in &item.content {
                                match block {
                                    RawContentBlock::InputText { text }
                                    | RawContentBlock::OutputText { text }
                                    | RawContentBlock::Text { text } => {
                                        text_parts.push(text.clone());
                                        raw_content.push(ContentBlock::Text {
                                            text: text.clone(),
                                        });
                                    }
                                    RawContentBlock::Thinking { thinking, .. } => {
                                        if let Some(t) = thinking {
                                            thinking_parts.push(t.clone());
                                            raw_content.push(ContentBlock::Thinking {
                                                thinking: t.clone(),
                                            });
                                        }
                                    }
                                    RawContentBlock::ToolUse { id, name, input } => {
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
                                    RawContentBlock::ToolResultBlock {
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
                                    RawContentBlock::Unknown => {
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
                        // "reasoning" items are encrypted in Codex; skip them.
                    }
                }

                _ => {
                    // event_msg etc. — not needed for session reconstruction.
                }
            }
        }

        // If we didn't find any session_meta, this isn't a valid Codex file.
        let id = session_id.unwrap_or_else(|| {
            // Derive from filename.
            path.file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
                .to_string()
        });

        // Determine session type: if approval_policy is "never" and there are
        // very few user messages, it's likely automated.
        let session_type = if metadata.permission_mode.as_deref() == Some("never")
            && messages
                .iter()
                .filter(|m| m.role == MessageRole::User)
                .count()
                <= 1
        {
            SessionType::Subagent
        } else if messages.iter().any(|m| m.role == MessageRole::User) {
            SessionType::Interactive
        } else {
            SessionType::Unknown
        };

        let session = Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::CodexCli,
            session_type,
            messages,
            metadata,
            environment,
        };

        Ok(vec![session])
    }
}

