//! Session type classifier: determine whether a session is interactive,
//! subagent, autonomous, or unknown.

use crate::session::{
    ContentBlock, Message, MessageClassification, MessageRole, Session, SessionType,
};

/// Classify a session as Interactive, Subagent, Autonomous, or Unknown.
///
/// Precedence is intentionally conservative:
/// - **Subagent** if explicit parser/path metadata already says subagent, the
///   path contains known subagent markers, or any user message carries a
///   `tool_result`/`tool_use_id` signal. This rule wins even if human-looking
///   classifications are also present.
/// - **Interactive** if any message has a `Human*` classification.
/// - **Autonomous** if there is at least one user message and zero `Human*`
///   classifications. This includes the ambiguous edge case where the only user
///   messages are `Unclassified`: not-human trumps not-known so the Interactive
///   stratum stays clean.
/// - **Unknown** otherwise.
pub fn classify_session(session: &Session) -> SessionType {
    if has_subagent_signal(session) {
        return SessionType::Subagent;
    }

    let has_user_messages = session.messages.iter().any(|m| m.role == MessageRole::User);

    if has_any_human_classification(session) {
        return SessionType::Interactive;
    }

    if has_user_messages {
        return SessionType::Autonomous;
    }

    SessionType::Unknown
}

fn has_subagent_signal(session: &Session) -> bool {
    if session.session_type == SessionType::Subagent {
        return true;
    }

    let path_str = session.source_path.to_string_lossy().to_lowercase();
    if path_str.contains("subagent") || path_str.contains("agent-a") {
        return true;
    }

    session
        .messages
        .iter()
        .filter(|m| m.role == MessageRole::User)
        .any(has_tool_result_signal)
}

fn has_tool_result_signal(message: &Message) -> bool {
    !message.tool_results.is_empty()
        || message
            .raw_content
            .iter()
            .any(|block| matches!(block, ContentBlock::ToolResultBlock { .. }))
}

fn has_any_human_classification(session: &Session) -> bool {
    session.messages.iter().any(|m| {
        matches!(
            m.classification,
            MessageClassification::HumanCorrection
                | MessageClassification::HumanDirective
                | MessageClassification::HumanApproval
                | MessageClassification::HumanQuestion
        )
    })
}
