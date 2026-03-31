//! Session type classifier: determine whether a session is interactive or subagent.

use crate::session::{MessageClassification, MessageRole, Session, SessionType};

/// Classify a session as Interactive, Subagent, or Unknown.
///
/// Rules:
/// - **Subagent** if the file path contains "subagent" or "agent-a", OR all
///   user messages are classified as `SystemMessage`.
/// - **Interactive** if the file path does NOT contain "subagent" AND the
///   session has at least one message classified as `HumanCorrection`,
///   `HumanDirective`, or `HumanApproval` (evidence of real human content).
/// - **Unknown** otherwise.
pub fn classify_session(session: &Session) -> SessionType {
    let path_str = session.source_path.to_string_lossy().to_lowercase();

    // Path-based subagent detection.
    if path_str.contains("subagent") || path_str.contains("agent-a") {
        return SessionType::Subagent;
    }

    let user_messages: Vec<_> = session
        .messages
        .iter()
        .filter(|m| m.role == MessageRole::User)
        .collect();

    // If there are user messages and ALL are system messages, it's a subagent session.
    if !user_messages.is_empty()
        && user_messages
            .iter()
            .all(|m| m.classification == MessageClassification::SystemMessage)
    {
        return SessionType::Subagent;
    }

    // Check for evidence of real human interaction.
    let has_human_content = session.messages.iter().any(|m| {
        matches!(
            m.classification,
            MessageClassification::HumanCorrection
                | MessageClassification::HumanDirective
                | MessageClassification::HumanApproval
        )
    });

    if has_human_content {
        SessionType::Interactive
    } else {
        SessionType::Unknown
    }
}

