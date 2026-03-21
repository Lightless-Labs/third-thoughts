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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::*;
    use std::path::PathBuf;

    fn make_session(path: &str, messages: Vec<Message>) -> Session {
        Session {
            id: "test-session".to_string(),
            source_path: PathBuf::from(path),
            source_tool: SourceTool::ClaudeCode,
            session_type: SessionType::Unknown,
            messages,
            metadata: SessionMetadata::default(),
            environment: EnvironmentFingerprint::default(),
        }
    }

    fn make_msg(role: MessageRole, classification: MessageClassification) -> Message {
        Message {
            role,
            timestamp: None,
            text: String::new(),
            thinking: None,
            tool_calls: vec![],
            tool_results: vec![],
            classification,
            raw_content: vec![],
        }
    }

    #[test]
    fn path_with_subagent_is_subagent() {
        let session = make_session(
            "/home/user/.claude/projects/subagent-task/session.jsonl",
            vec![make_msg(MessageRole::User, MessageClassification::HumanDirective)],
        );
        assert_eq!(classify_session(&session), SessionType::Subagent);
    }

    #[test]
    fn path_with_agent_a_is_subagent() {
        let session = make_session(
            "/tmp/agent-a/run.jsonl",
            vec![make_msg(MessageRole::User, MessageClassification::HumanDirective)],
        );
        assert_eq!(classify_session(&session), SessionType::Subagent);
    }

    #[test]
    fn all_system_messages_is_subagent() {
        let session = make_session(
            "/home/user/.claude/projects/task/session.jsonl",
            vec![
                make_msg(MessageRole::User, MessageClassification::SystemMessage),
                make_msg(MessageRole::Assistant, MessageClassification::Other),
                make_msg(MessageRole::User, MessageClassification::SystemMessage),
            ],
        );
        assert_eq!(classify_session(&session), SessionType::Subagent);
    }

    #[test]
    fn human_directive_is_interactive() {
        let session = make_session(
            "/home/user/.claude/projects/task/session.jsonl",
            vec![
                make_msg(MessageRole::User, MessageClassification::HumanDirective),
                make_msg(MessageRole::Assistant, MessageClassification::Other),
            ],
        );
        assert_eq!(classify_session(&session), SessionType::Interactive);
    }

    #[test]
    fn human_correction_is_interactive() {
        let session = make_session(
            "/home/user/.claude/projects/task/session.jsonl",
            vec![
                make_msg(MessageRole::User, MessageClassification::SystemMessage),
                make_msg(MessageRole::User, MessageClassification::HumanCorrection),
            ],
        );
        assert_eq!(classify_session(&session), SessionType::Interactive);
    }

    #[test]
    fn no_messages_is_unknown() {
        let session = make_session("/tmp/session.jsonl", vec![]);
        assert_eq!(classify_session(&session), SessionType::Unknown);
    }

    #[test]
    fn only_assistant_messages_is_unknown() {
        let session = make_session(
            "/tmp/session.jsonl",
            vec![make_msg(MessageRole::Assistant, MessageClassification::Other)],
        );
        assert_eq!(classify_session(&session), SessionType::Unknown);
    }
}
