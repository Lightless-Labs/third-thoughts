//! Cucumber step definitions for the `redact-thinking-2026-02-12`
//! thinking-visibility stratification feature.

use std::path::PathBuf;

use cucumber::{given, then};

use middens::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool, ThinkingVisibility,
};

use super::world::MiddensWorld;

fn mk_assistant(thinking: Option<&str>, text: &str) -> Message {
    let mut raw_content = Vec::new();
    if let Some(t) = thinking {
        raw_content.push(ContentBlock::Thinking {
            thinking: t.to_string(),
        });
    }
    raw_content.push(ContentBlock::Text {
        text: text.to_string(),
    });
    let reasoning_observability = if thinking.is_some() {
        middens::session::ReasoningObservability::FullTextVisible
    } else {
        middens::session::ReasoningObservability::Absent
    };
    Message {
        role: MessageRole::Assistant,
        timestamp: None,
        text: text.to_string(),
        thinking: thinking.map(ToOwned::to_owned),
        reasoning_summary: None,
        reasoning_observability,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::Other,
        raw_content,
    }
}

fn mk_user(text: &str) -> Message {
    Message {
        role: MessageRole::User,
        timestamp: None,
        text: text.to_string(),
        thinking: None,
        reasoning_summary: None,
        reasoning_observability: middens::session::ReasoningObservability::Absent,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::HumanDirective,
        raw_content: vec![ContentBlock::Text {
            text: text.to_string(),
        }],
    }
}

fn mk_session(
    id: &str,
    thinking: Option<&str>,
    text: &str,
    visibility: ThinkingVisibility,
) -> Session {
    Session {
        id: id.to_string(),
        source_path: PathBuf::from(format!("/tmp/{}.jsonl", id)),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages: vec![mk_user("Analyze this."), mk_assistant(thinking, text)],
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: visibility,
        reasoning_observability: middens::session::SessionReasoningObservability::Unknown,
    }
}

#[given("an all-visible fixture with suppressed risk tokens")]
fn given_all_visible(world: &mut MiddensWorld) {
    world.sessions = vec![
        mk_session(
            "visible-1",
            Some("password secret token vulnerability"),
            "All good, proceeding.",
            ThinkingVisibility::Visible,
        ),
        mk_session(
            "visible-2",
            Some("risk concern worry"),
            "Done.",
            ThinkingVisibility::Visible,
        ),
    ];
}

#[given(expr = "an all-redacted fixture with {int} sessions")]
fn given_all_redacted(world: &mut MiddensWorld, count: usize) {
    world.sessions = (0..count)
        .map(|i| {
            mk_session(
                &format!("redacted-{}", i),
                None,
                "Public answer only.",
                ThinkingVisibility::Redacted,
            )
        })
        .collect();
}

#[given(expr = "a mixed fixture with {int} visible and {int} redacted sessions")]
fn given_mixed(world: &mut MiddensWorld, n_visible: usize, n_redacted: usize) {
    let mut sessions = Vec::new();
    for i in 0..n_visible {
        sessions.push(mk_session(
            &format!("mix-vis-{}", i),
            Some("password secret token"),
            "Public-safe answer.",
            ThinkingVisibility::Visible,
        ));
    }
    for i in 0..n_redacted {
        sessions.push(mk_session(
            &format!("mix-red-{}", i),
            None,
            "Public answer.",
            ThinkingVisibility::Redacted,
        ));
    }
    world.sessions = sessions;
}

#[then(expr = "the thinking divergence summary should mention {string}")]
fn then_summary_mentions(world: &mut MiddensWorld, needle: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    assert!(
        result.summary.contains(&needle),
        "expected summary to contain {:?}, got: {}",
        needle,
        result.summary
    );
}
