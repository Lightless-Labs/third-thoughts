use cucumber::{given, then, when};
use std::path::PathBuf;

use middens::classifier::correction::classify_message;
use middens::classifier::session_type::classify_session;
use middens::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool,
};

use super::world::MiddensWorld;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn parse_classification(s: &str) -> MessageClassification {
    match s {
        "HumanCorrection" => MessageClassification::HumanCorrection,
        "HumanDirective" => MessageClassification::HumanDirective,
        "HumanApproval" => MessageClassification::HumanApproval,
        "HumanQuestion" => MessageClassification::HumanQuestion,
        "SystemMessage" => MessageClassification::SystemMessage,
        "Other" => MessageClassification::Other,
        "Unclassified" => MessageClassification::Unclassified,
        other => panic!("Unknown MessageClassification variant: {other}"),
    }
}

fn parse_session_type(s: &str) -> SessionType {
    match s {
        "Interactive" => SessionType::Interactive,
        "Subagent" => SessionType::Subagent,
        "Unknown" => SessionType::Unknown,
        other => panic!("Unknown SessionType variant: {other}"),
    }
}

fn make_message(role: MessageRole, classification: MessageClassification) -> Message {
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

fn user_msg(text: &str) -> Message {
    Message {
        role: MessageRole::User,
        timestamp: None,
        text: text.to_string(),
        thinking: None,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::Unclassified,
        raw_content: vec![],
    }
}

fn user_msg_with_tool_result(text: &str) -> Message {
    Message {
        role: MessageRole::User,
        timestamp: None,
        text: text.to_string(),
        thinking: None,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::Unclassified,
        raw_content: vec![ContentBlock::ToolResultBlock {
            tool_use_id: "toolu_123".to_string(),
            content: serde_json::json!("result"),
            is_error: false,
        }],
    }
}

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

// ---------------------------------------------------------------------------
// Given steps — correction classifier
// ---------------------------------------------------------------------------

/// Store a plain user message for later classification.
#[given(expr = "a user message {string}")]
fn given_user_message(world: &mut MiddensWorld, text: String) {
    // Stash the message as a single-message session so we can retrieve it in `when`.
    let msg = user_msg(&text);
    world.sessions = vec![make_session("/test/session.jsonl", vec![msg])];
}

/// Store a user message that contains a tool_result content block.
#[given(expr = "a user message {string} with a tool_result content block")]
fn given_user_message_with_tool_result(world: &mut MiddensWorld, text: String) {
    let msg = user_msg_with_tool_result(&text);
    world.sessions = vec![make_session("/test/session.jsonl", vec![msg])];
}

/// Store a user message consisting of `count` repeated copies of `ch`.
#[given(expr = "a user message of {int} repeated {string} characters")]
fn given_repeated_char_message(world: &mut MiddensWorld, count: usize, ch: String) {
    let text = ch.repeat(count);
    let msg = user_msg(&text);
    world.sessions = vec![make_session("/test/session.jsonl", vec![msg])];
}

/// Store an assistant message for later classification.
#[given(expr = "an assistant message {string}")]
fn given_assistant_message(world: &mut MiddensWorld, text: String) {
    let msg = Message {
        role: MessageRole::Assistant,
        timestamp: None,
        text: text.to_string(),
        thinking: None,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::Unclassified,
        raw_content: vec![],
    };
    world.sessions = vec![make_session("/test/session.jsonl", vec![msg])];
}

// ---------------------------------------------------------------------------
// Given steps — session type classifier
// ---------------------------------------------------------------------------

/// Initialise an empty session from a specific path.
#[given(expr = "a session from path {string}")]
fn given_session_from_path(world: &mut MiddensWorld, path: String) {
    world.sessions = vec![make_session(&path, vec![])];
}

/// Append a user message with a given classification to the current session.
#[given(expr = "the session has a user message classified as {string}")]
fn given_session_has_user_message(world: &mut MiddensWorld, classification: String) {
    let cls = parse_classification(&classification);
    let msg = make_message(MessageRole::User, cls);
    world.sessions[0].messages.push(msg);
}

/// Append an assistant message with a given classification to the current session.
#[given(expr = "the session has an assistant message classified as {string}")]
fn given_session_has_assistant_message(world: &mut MiddensWorld, classification: String) {
    let cls = parse_classification(&classification);
    let msg = make_message(MessageRole::Assistant, cls);
    world.sessions[0].messages.push(msg);
}

// ---------------------------------------------------------------------------
// When steps
// ---------------------------------------------------------------------------

/// Classify the stored message. Position is either "first" or "middle".
#[when(expr = "I classify the message at position {string}")]
fn when_classify_message(world: &mut MiddensWorld, position: String) {
    let is_first = position == "first";
    let msg = &world.sessions[0].messages[0];
    world.classified_message = Some(classify_message(msg, is_first));
}

/// Classify the stored session's type.
#[when("I classify the session type")]
fn when_classify_session_type(world: &mut MiddensWorld) {
    let session = &world.sessions[0];
    world.classified_type = Some(classify_session(session));
}

// ---------------------------------------------------------------------------
// Then steps
// ---------------------------------------------------------------------------

/// Assert the message classification result.
#[then(expr = "the message should be classified as {string}")]
fn then_message_classified_as(world: &mut MiddensWorld, expected: String) {
    let actual = world
        .classified_message
        .expect("No message classification result — did the When step run?");
    let expected = parse_classification(&expected);
    assert_eq!(
        actual, expected,
        "Expected message classification {expected:?}, got {actual:?}"
    );
}

/// Assert the session type classification result.
#[then(expr = "the session type should be {string}")]
fn then_session_type_is(world: &mut MiddensWorld, expected: String) {
    let actual = world
        .classified_type
        .expect("No session type result — did the When step run?");
    let expected = parse_session_type(&expected);
    assert_eq!(
        actual, expected,
        "Expected session type {expected:?}, got {actual:?}"
    );
}
