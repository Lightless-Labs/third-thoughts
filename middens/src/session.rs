//! Unified session and message types parsed from any agent tool format.

use std::collections::BTreeMap;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A parsed session from any supported agent tool.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Session {
    /// Unique session identifier (from the source file or generated).
    pub id: String,
    /// Path to the source file this session was parsed from.
    pub source_path: PathBuf,
    /// Which agent tool produced this session.
    pub source_tool: SourceTool,
    /// Session type: interactive (human-in-the-loop) or subagent (automated).
    pub session_type: SessionType,
    /// All messages in chronological order.
    pub messages: Vec<Message>,
    /// Session-level metadata extracted from the source.
    pub metadata: SessionMetadata,
    /// Environment fingerprint: what was active when this session ran.
    pub environment: EnvironmentFingerprint,
    /// Whether thinking blocks are visible in this transcript.
    ///
    /// Placed on `Session` rather than `SessionMetadata` because it is a
    /// derived property of the entire message stream (not a passively parsed
    /// field), and downstream techniques must branch on it frequently.
    #[serde(default)]
    pub thinking_visibility: ThinkingVisibility,
    /// Session-level reasoning observability derived from message-level labels.
    ///
    /// This is distinct from `thinking_visibility`: provider traces can expose
    /// plaintext summaries while keeping raw reasoning encrypted/signature-only.
    #[serde(default)]
    pub reasoning_observability: SessionReasoningObservability,
}

/// Which agent tool produced this session.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SourceTool {
    ClaudeCode,
    CodexCli,
    GeminiCli,
    Cursor,
    OpenClaw,
    OpenCode,
    Unknown,
}

impl std::fmt::Display for SourceTool {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::ClaudeCode => write!(f, "Claude Code"),
            Self::CodexCli => write!(f, "Codex CLI"),
            Self::GeminiCli => write!(f, "Gemini CLI"),
            Self::Cursor => write!(f, "Cursor"),
            Self::OpenClaw => write!(f, "OpenClaw"),
            Self::OpenCode => write!(f, "OpenCode"),
            Self::Unknown => write!(f, "Unknown"),
        }
    }
}

/// Whether thinking blocks are present in the transcript.
///
/// On 2026-02-12 Anthropic rolled out the `redact-thinking-2026-02-12` beta
/// header which hides thinking blocks from the Claude Code UI to reduce
/// latency. Crucially, thinking still happens server-side; it simply is no
/// longer written to local session transcripts. Any technique that counts
/// thinking blocks in transcripts therefore measures *transcript presence*,
/// not *actual thinking*.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum ThinkingVisibility {
    /// Thinking blocks are present in the transcript (pre-Feb-12 or opted-in).
    Visible,
    /// Thinking is happening but not stored in the transcript (post-Feb-12 default).
    Redacted,
    /// Cannot be determined from the available data.
    #[default]
    Unknown,
}

/// Message-level observability of private reasoning in the transcript.
///
/// `SummaryVisible` is deliberately separate from `FullTextVisible`: summaries
/// are provider/model-selected abstractions, not raw chain-of-thought. Techniques
/// that compare `Message::thinking` against public text must not silently treat
/// summaries as raw thinking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum ReasoningObservability {
    /// Raw/full reasoning text is present in `Message::thinking`.
    FullTextVisible,
    /// A plaintext reasoning summary is present while raw reasoning is opaque.
    SummaryVisible,
    /// A reasoning/signature block exists, but no plaintext is present.
    SignatureOnly,
    /// No reasoning block was recorded for this message.
    Absent,
    /// Cannot be determined from the available data.
    #[default]
    Unknown,
}

/// Session-level rollup of message-level reasoning observability labels.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum SessionReasoningObservability {
    FullTextVisible,
    SummaryVisible,
    SignatureOnly,
    Mixed,
    Absent,
    #[default]
    Unknown,
}

/// Whether this session involved a human or was automated.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SessionType {
    /// Human-in-the-loop: real user corrections and steering.
    Interactive,
    /// Automated: subagent or autonomous loop with minimal/no human contact.
    Subagent,
    /// Could not determine.
    Unknown,
}

/// A single message in a session (from any role).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    /// Message role.
    pub role: MessageRole,
    /// Timestamp of this message.
    pub timestamp: Option<DateTime<Utc>>,
    /// The public text content (what the user sees).
    pub text: String,
    /// Private thinking/reasoning content (if raw/full text is preserved).
    pub thinking: Option<String>,
    /// Provider/model-selected reasoning summary, if present.
    ///
    /// This must stay separate from `thinking`: summary-visible traces measure a
    /// different phenomenon than raw private reasoning.
    #[serde(default)]
    pub reasoning_summary: Option<String>,
    /// How much private reasoning is observable for this message.
    #[serde(default)]
    pub reasoning_observability: ReasoningObservability,
    /// Tool calls made in this message.
    pub tool_calls: Vec<ToolCall>,
    /// Tool results returned in this message.
    pub tool_results: Vec<ToolResult>,
    /// Classification of this message (correction, directive, approval, etc.).
    pub classification: MessageClassification,
    /// Raw content blocks from the source (for techniques that need them).
    pub raw_content: Vec<ContentBlock>,
}

/// Message role.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MessageRole {
    User,
    Assistant,
    System,
}

/// Classification of a user message.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MessageClassification {
    /// Real human correcting agent behavior.
    HumanCorrection,
    /// New instruction or task from a human.
    HumanDirective,
    /// Human approving or accepting agent output.
    HumanApproval,
    /// Human asking a question.
    HumanQuestion,
    /// Tool result, system notification, hook output.
    SystemMessage,
    /// Everything else.
    Other,
    /// Not yet classified.
    Unclassified,
}

/// A tool call made by the assistant.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Tool call ID (for matching with results).
    pub id: String,
    /// Tool name (e.g., "Bash", "Read", "Edit").
    pub name: String,
    /// Tool input as a JSON value.
    pub input: serde_json::Value,
}

/// A tool result returned to the assistant.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    /// Tool use ID this result corresponds to.
    pub tool_use_id: String,
    /// Result content (text).
    pub content: String,
    /// Whether the tool execution errored.
    pub is_error: bool,
}

/// A raw content block from the source JSONL.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "thinking")]
    Thinking { thinking: String },
    #[serde(rename = "reasoning_summary")]
    ReasoningSummary { text: String },
    #[serde(rename = "reasoning_signature")]
    ReasoningSignature,
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
    #[serde(rename = "tool_result")]
    ToolResultBlock {
        tool_use_id: String,
        content: serde_json::Value,
        #[serde(default)]
        is_error: bool,
    },
    /// Catch-all for unknown block types.
    #[serde(other)]
    Unknown,
}

/// Session-level metadata extracted from the source.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SessionMetadata {
    /// Agent tool version string.
    pub version: Option<String>,
    /// Working directory.
    pub cwd: Option<String>,
    /// Git branch.
    pub git_branch: Option<String>,
    /// Model ID used.
    pub model: Option<String>,
    /// Project path or identifier.
    pub project: Option<String>,
    /// Permission mode.
    pub permission_mode: Option<String>,
    /// Additional tool-specific fields.
    pub extra: BTreeMap<String, serde_json::Value>,
}

/// Environment fingerprint: the configuration active during this session.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EnvironmentFingerprint {
    /// Agent tool version.
    pub tool_version: Option<String>,
    /// Model identifier.
    pub model_id: Option<String>,
    /// Permission/approval mode.
    pub permission_mode: Option<String>,
    /// Hash of CLAUDE.md (or equivalent) content if detectable.
    pub config_hash: Option<String>,
    /// MCP servers detected in session.
    pub mcp_servers: Vec<String>,
    /// Plugins/skills detected in session.
    pub plugins: Vec<String>,
    /// Hooks detected in session.
    pub hooks: Vec<String>,
}

impl SessionReasoningObservability {
    /// Derive a session-level label from message-level observability.
    ///
    /// `Absent` user/system messages do not make an otherwise summary-visible
    /// or full-text-visible session `Mixed`; only multiple concrete reasoning
    /// modes do. This keeps the label aligned with the reasoning blocks that
    /// actually exist in the transcript.
    ///
    /// `Unknown` is conservative: if any message is unknown, the whole session
    /// is unknown unless there are multiple concrete modes, in which case the
    /// concrete heterogeneity is still reported as `Mixed`.
    pub fn from_messages(messages: &[Message]) -> Self {
        let mut has_full_text = false;
        let mut has_summary = false;
        let mut has_signature_only = false;
        let mut has_unknown = false;

        for message in messages {
            match message.reasoning_observability {
                ReasoningObservability::FullTextVisible => has_full_text = true,
                ReasoningObservability::SummaryVisible => has_summary = true,
                ReasoningObservability::SignatureOnly => has_signature_only = true,
                ReasoningObservability::Unknown => has_unknown = true,
                ReasoningObservability::Absent => {}
            }
        }

        let concrete_modes =
            usize::from(has_full_text) + usize::from(has_summary) + usize::from(has_signature_only);

        match concrete_modes {
            0 if has_unknown => Self::Unknown,
            0 => Self::Absent,
            1 if has_unknown => Self::Unknown,
            1 if has_full_text => Self::FullTextVisible,
            1 if has_summary => Self::SummaryVisible,
            1 if has_signature_only => Self::SignatureOnly,
            _ => Self::Mixed,
        }
    }
}

impl Session {
    /// Count of user messages (any role == User).
    pub fn user_message_count(&self) -> usize {
        self.messages
            .iter()
            .filter(|m| m.role == MessageRole::User)
            .count()
    }

    /// Count of assistant messages.
    pub fn assistant_message_count(&self) -> usize {
        self.messages
            .iter()
            .filter(|m| m.role == MessageRole::Assistant)
            .count()
    }

    /// Count of all tool calls across all messages.
    pub fn total_tool_calls(&self) -> usize {
        self.messages.iter().map(|m| m.tool_calls.len()).sum()
    }

    /// Count of messages classified as corrections.
    pub fn correction_count(&self) -> usize {
        self.messages
            .iter()
            .filter(|m| m.classification == MessageClassification::HumanCorrection)
            .count()
    }

    /// Count of messages with thinking blocks.
    pub fn thinking_count(&self) -> usize {
        self.messages
            .iter()
            .filter(|m| m.thinking.is_some())
            .count()
    }

    /// Total text length across all messages.
    pub fn total_text_length(&self) -> usize {
        self.messages.iter().map(|m| m.text.len()).sum()
    }

    /// Total thinking text length.
    pub fn total_thinking_length(&self) -> usize {
        self.messages
            .iter()
            .filter_map(|m| m.thinking.as_ref())
            .map(|t| t.len())
            .sum()
    }

    /// Ordered list of tool names used (for sequence analysis).
    pub fn tool_sequence(&self) -> Vec<&str> {
        self.messages
            .iter()
            .flat_map(|m| m.tool_calls.iter())
            .map(|tc| tc.name.as_str())
            .collect()
    }
}
