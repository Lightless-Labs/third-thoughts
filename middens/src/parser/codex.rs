use std::io::BufRead;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::Deserialize;

use super::SessionParser;
use crate::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole,
    ReasoningObservability, Session, SessionMetadata, SessionReasoningObservability, SessionType,
    SourceTool, ToolCall, ToolResult,
};

pub struct CodexParser;

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

#[derive(Debug)]
struct ReasoningSummaryExtraction {
    raw_text: String,
    display_text: String,
}

fn extract_reasoning_summary(
    summary: Option<&serde_json::Value>,
    thinking_signature: Option<&serde_json::Value>,
) -> Option<ReasoningSummaryExtraction> {
    let mut raw_parts = Vec::new();
    if let Some(summary) = summary {
        collect_text_fields(summary, &mut raw_parts);
    }
    if let Some(signature_summary) =
        thinking_signature.and_then(|signature| signature.get("summary"))
    {
        collect_text_fields(signature_summary, &mut raw_parts);
    }

    if raw_parts.is_empty() {
        return None;
    }

    let raw_text = raw_parts.join("\n");
    let mut display_parts = raw_parts;
    let mut seen = std::collections::HashSet::new();
    display_parts.retain(|part| seen.insert(part.clone()));

    Some(ReasoningSummaryExtraction {
        raw_text,
        display_text: display_parts.join("\n"),
    })
}

fn collect_text_fields(value: &serde_json::Value, parts: &mut Vec<String>) {
    enum Action<'a> {
        Visit(&'a serde_json::Value),
        PushText(&'a str),
    }

    let mut stack = vec![Action::Visit(value)];
    while let Some(action) = stack.pop() {
        match action {
            Action::PushText(text) => {
                if !text.trim().is_empty() {
                    parts.push(text.to_string());
                }
            }
            Action::Visit(serde_json::Value::String(text)) => {
                if !text.trim().is_empty() {
                    parts.push(text.clone());
                }
            }
            Action::Visit(serde_json::Value::Array(items)) => {
                for item in items.iter().rev() {
                    stack.push(Action::Visit(item));
                }
            }
            Action::Visit(serde_json::Value::Object(map)) => {
                let mut actions = Vec::new();
                for (key, item) in map {
                    if key == "text" {
                        if let Some(text) = item.as_str() {
                            actions.push(Action::PushText(text));
                            continue;
                        }
                    }
                    if item.is_array() || item.is_object() {
                        actions.push(Action::Visit(item));
                    }
                }
                for action in actions.into_iter().rev() {
                    stack.push(action);
                }
            }
            Action::Visit(_) => {}
        }
    }
}

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
    InputText { text: String },
    #[serde(rename = "output_text")]
    OutputText { text: String },
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "thinking")]
    Thinking {
        thinking: Option<String>,
        #[serde(default)]
        summary: Option<serde_json::Value>,
        #[serde(default, rename = "thinkingSignature")]
        thinking_signature: Option<serde_json::Value>,
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
                    eprintln!(
                        "warning: skipping unreadable line in {}: {e}",
                        path.display()
                    );
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
                            metadata.extra.insert(
                                "model_provider".into(),
                                serde_json::Value::String(provider),
                            );
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
                            metadata.extra.insert(
                                "personality".into(),
                                serde_json::Value::String(personality),
                            );
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
                            let mut reasoning_summary_parts: Vec<String> = Vec::new();
                            let mut reasoning_observability = ReasoningObservability::Absent;
                            let mut tool_calls: Vec<ToolCall> = Vec::new();
                            let mut tool_results: Vec<ToolResult> = Vec::new();
                            let mut raw_content: Vec<ContentBlock> = Vec::new();

                            for block in &item.content {
                                match block {
                                    RawContentBlock::InputText { text }
                                    | RawContentBlock::OutputText { text }
                                    | RawContentBlock::Text { text } => {
                                        text_parts.push(text.clone());
                                        raw_content.push(ContentBlock::Text { text: text.clone() });
                                    }
                                    RawContentBlock::Thinking {
                                        thinking,
                                        summary,
                                        thinking_signature,
                                    } => {
                                        let thinking_text = thinking
                                            .as_deref()
                                            .filter(|text| !text.trim().is_empty());
                                        let summary_extraction = extract_reasoning_summary(
                                            summary.as_ref(),
                                            thinking_signature.as_ref(),
                                        );
                                        let has_signature = thinking_signature.is_some();

                                        if has_signature {
                                            if let Some(summary_extraction) = summary_extraction {
                                                let summary_text = summary_extraction.display_text;
                                                if let Some(thinking_text) = thinking_text {
                                                    let thinking_text = thinking_text.trim();
                                                    let matches_raw = thinking_text
                                                        == summary_extraction.raw_text.trim();
                                                    let matches_display =
                                                        thinking_text == summary_text.trim();
                                                    if !matches_raw && !matches_display {
                                                        anyhow::bail!(
                                                            "{}",
                                                            "unsupported Codex thinking block: thinkingSignature summary and plaintext thinking differ; expected matching summary text, omitted plaintext thinking, or no thinkingSignature for raw visible thinking. Example supported summary block: {\"type\":\"thinking\",\"thinking\":\"reasoning summary\",\"thinkingSignature\":{\"summary\":[{\"text\":\"reasoning summary\"}]}}"
                                                        );
                                                    }
                                                }
                                                reasoning_summary_parts.push(summary_text.clone());
                                                reasoning_observability =
                                                    merge_reasoning_observability(
                                                        reasoning_observability,
                                                        ReasoningObservability::SummaryVisible,
                                                    );
                                                raw_content.push(ContentBlock::ReasoningSummary {
                                                    text: summary_text,
                                                });
                                            } else if thinking_text.is_some() {
                                                anyhow::bail!(
                                                    "{}",
                                                    "unsupported Codex thinking block: thinkingSignature is present with plaintext thinking but no explicit summary; expected summary in payload.summary or thinkingSignature.summary, or omit thinkingSignature for raw visible thinking. Example supported summary block: {\"type\":\"thinking\",\"thinking\":\"\",\"thinkingSignature\":{\"summary\":[{\"text\":\"reasoning summary\"}]}}"
                                                );
                                            } else {
                                                reasoning_observability =
                                                    merge_reasoning_observability(
                                                        reasoning_observability,
                                                        ReasoningObservability::SignatureOnly,
                                                    );
                                                raw_content.push(ContentBlock::ReasoningSignature);
                                            }
                                        } else if let Some(t) = thinking_text {
                                            thinking_parts.push(t.to_string());
                                            reasoning_observability = merge_reasoning_observability(
                                                reasoning_observability,
                                                ReasoningObservability::FullTextVisible,
                                            );
                                            raw_content.push(ContentBlock::Thinking {
                                                thinking: t.to_string(),
                                            });
                                        } else if let Some(summary_extraction) = summary_extraction
                                        {
                                            let summary_text = summary_extraction.display_text;
                                            reasoning_summary_parts.push(summary_text.clone());
                                            reasoning_observability = merge_reasoning_observability(
                                                reasoning_observability,
                                                ReasoningObservability::SummaryVisible,
                                            );
                                            raw_content.push(ContentBlock::ReasoningSummary {
                                                text: summary_text,
                                            });
                                        } else {
                                            // Degenerate thinking block with no signature, no
                                            // plaintext, and no summary. Treat it as absent rather
                                            // than fabricating a signature marker.
                                            reasoning_observability = merge_reasoning_observability(
                                                reasoning_observability,
                                                ReasoningObservability::Absent,
                                            );
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
                                        reasoning_observability = merge_reasoning_observability(
                                            reasoning_observability,
                                            ReasoningObservability::Unknown,
                                        );
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
                            let reasoning_summary = if reasoning_summary_parts.is_empty() {
                                None
                            } else {
                                Some(reasoning_summary_parts.join("\n"))
                            };

                            messages.push(Message {
                                role,
                                timestamp: ts,
                                text,
                                thinking,
                                reasoning_summary,
                                reasoning_observability,
                                tool_calls,
                                tool_results,
                                classification: MessageClassification::Unclassified,
                                raw_content,
                            });
                        } else if item_type == "reasoning" {
                            anyhow::bail!(
                                "{}",
                                "unsupported Codex response_item.payload.type=\"reasoning\"; expected payload.type=\"message\" until standalone reasoning items are modelled. Example supported item: {\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"ok\"}]}}"
                            );
                        }
                        // Reasoning blocks embedded in messages are handled above and labelled
                        // as full-text, summary, or signature-only. Standalone `reasoning`
                        // response_items fail clearly until the session model grows an event
                        // stream or synthetic-message representation for them.
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

        let reasoning_observability = SessionReasoningObservability::from_messages(&messages);

        let session = Session {
            id,
            source_path: path.to_path_buf(),
            source_tool: SourceTool::CodexCli,
            session_type,
            messages,
            metadata,
            environment,
            thinking_visibility: crate::session::ThinkingVisibility::Unknown,
            reasoning_observability,
        };

        Ok(vec![session])
    }
}
