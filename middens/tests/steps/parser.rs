use std::path::PathBuf;

use cucumber::{gherkin::Step, given, then, when};
use tempfile::TempDir;

use middens::parser::SessionParser;
use middens::parser::auto_detect::{detect_format, parse_auto};
use middens::parser::claude_code::ClaudeCodeParser;
use middens::parser::codex::CodexParser;
use middens::parser::openclaw::OpenClawParser;

use super::world::MiddensWorld;

// ---------------------------------------------------------------------------
// Given steps
// ---------------------------------------------------------------------------

/// Set file_path to a fixture relative to CARGO_MANIFEST_DIR.
#[given(expr = "a session file {string}")]
fn given_session_file(world: &mut MiddensWorld, relative_path: String) {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative_path);
    assert!(path.exists(), "fixture not found: {}", path.display());
    world.file_path = Some(path);
}

/// Set file_path to an arbitrary path (may not exist on disk).
#[given(expr = "a session file path {string}")]
fn given_session_file_path(world: &mut MiddensWorld, path: String) {
    world.file_path = Some(PathBuf::from(path));
}

/// Create a temporary JSONL file with the given content (from a docstring).
#[given("a temporary JSONL file with content:")]
fn given_temp_jsonl(world: &mut MiddensWorld, step: &Step) {
    let content = step.docstring().expect("missing docstring content");
    let tmp = TempDir::new().expect("failed to create temp dir");
    let file = tmp.path().join("session.jsonl");
    std::fs::write(&file, content.trim()).expect("failed to write temp file");
    world.file_path = Some(file);
    world.temp_dir = Some(tmp);
}

// ---------------------------------------------------------------------------
// When steps — can_parse checks
// ---------------------------------------------------------------------------

#[when("I check if the Claude Code parser can parse it")]
fn when_claude_code_can_parse(world: &mut MiddensWorld) {
    let parser = ClaudeCodeParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    let result = parser.can_parse(path);
    // Store as numeric_result: 1.0 = parseable, 0.0 = not.
    world.numeric_result = Some(if result { 1.0 } else { 0.0 });
}

#[when("I check if the Codex parser can parse it")]
fn when_codex_can_parse(world: &mut MiddensWorld) {
    let parser = CodexParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    let result = parser.can_parse(path);
    world.numeric_result = Some(if result { 1.0 } else { 0.0 });
}

#[when("I check if the OpenClaw parser can parse it")]
fn when_openclaw_can_parse(world: &mut MiddensWorld) {
    let parser = OpenClawParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    let result = parser.can_parse(path);
    world.numeric_result = Some(if result { 1.0 } else { 0.0 });
}

// ---------------------------------------------------------------------------
// When steps — parse
// ---------------------------------------------------------------------------

#[when("I parse the file with the Claude Code parser")]
fn when_parse_claude_code(world: &mut MiddensWorld) {
    let parser = ClaudeCodeParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    match parser.parse(path) {
        Ok(sessions) => world.sessions = sessions,
        Err(e) => world.error = Some(format!("{e:#}")),
    }
}

#[when("I parse the file with the Codex parser")]
fn when_parse_codex(world: &mut MiddensWorld) {
    let parser = CodexParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    match parser.parse(path) {
        Ok(sessions) => world.sessions = sessions,
        Err(e) => world.error = Some(format!("{e:#}")),
    }
}

#[when("I parse the file with the OpenClaw parser")]
fn when_parse_openclaw(world: &mut MiddensWorld) {
    let parser = OpenClawParser;
    let path = world.file_path.as_ref().expect("file_path not set");
    // Reset state before storing new results to prevent stale data assertions.
    world.sessions.clear();
    world.error = None;
    match parser.parse(path) {
        Ok(sessions) => world.sessions = sessions,
        Err(e) => world.error = Some(format!("{e:#}")),
    }
}

// ---------------------------------------------------------------------------
// When steps — auto-detect
// ---------------------------------------------------------------------------

#[when("I detect the format")]
fn when_detect_format(world: &mut MiddensWorld) {
    let path = world.file_path.as_ref().expect("file_path not set");
    world.detected_format = detect_format(path);
}

#[when("I detect the format from the path")]
fn when_detect_format_from_path(world: &mut MiddensWorld) {
    let path = world.file_path.as_ref().expect("file_path not set");
    world.detected_format = detect_format(path);
}

#[when("I auto-parse the file")]
fn when_auto_parse(world: &mut MiddensWorld) {
    let path = world.file_path.as_ref().expect("file_path not set");
    // Reset state before storing new results.
    world.sessions.clear();
    world.error = None;
    match parse_auto(path) {
        Ok(sessions) => world.sessions = sessions,
        Err(e) => world.error = Some(format!("{e:#}")),
    }
}

// ---------------------------------------------------------------------------
// Then steps — can_parse assertions
// ---------------------------------------------------------------------------

#[then("it should be parseable")]
fn then_parseable(world: &mut MiddensWorld) {
    let val = world.numeric_result.expect("numeric_result not set");
    assert_eq!(val, 1.0, "expected file to be parseable");
}

#[then("it should not be parseable")]
fn then_not_parseable(world: &mut MiddensWorld) {
    let val = world.numeric_result.expect("numeric_result not set");
    assert_eq!(val, 0.0, "expected file to NOT be parseable");
}

// ---------------------------------------------------------------------------
// Then steps — session count and basic fields
// ---------------------------------------------------------------------------

#[then(expr = "there should be {int} session(s)")]
fn then_session_count(world: &mut MiddensWorld, expected: usize) {
    assert_eq!(
        world.sessions.len(),
        expected,
        "expected {} session(s), got {}",
        expected,
        world.sessions.len()
    );
}

#[then(expr = "the session id should be {string}")]
fn then_session_id(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(session.id, expected);
}

#[then(expr = "the source tool should be {string}")]
fn then_source_tool(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    let actual = format!("{:?}", session.source_tool);
    assert_eq!(actual, expected, "source tool mismatch");
}

#[then(expr = "the parsed session type should be {string}")]
fn then_parsed_session_type(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    let actual = format!("{:?}", session.session_type);
    assert_eq!(actual, expected, "session type mismatch");
}

// ---------------------------------------------------------------------------
// Then steps — metadata
// ---------------------------------------------------------------------------

#[then(expr = "the metadata version should be {string}")]
fn then_metadata_version(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(session.metadata.version.as_deref(), Some(expected.as_str()));
}

#[then(expr = "the metadata cwd should be {string}")]
fn then_metadata_cwd(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(session.metadata.cwd.as_deref(), Some(expected.as_str()));
}

#[then(expr = "the metadata git branch should be {string}")]
fn then_metadata_git_branch(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(
        session.metadata.git_branch.as_deref(),
        Some(expected.as_str())
    );
}

#[then(expr = "the metadata permission mode should be {string}")]
fn then_metadata_permission_mode(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(
        session.metadata.permission_mode.as_deref(),
        Some(expected.as_str())
    );
}

#[then(expr = "the metadata model should be {string}")]
fn then_metadata_model(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(session.metadata.model.as_deref(), Some(expected.as_str()));
}

#[then("the metadata model should be present")]
fn then_metadata_model_present(world: &mut MiddensWorld) {
    let session = &world.sessions[0];
    assert!(
        session.metadata.model.is_some(),
        "expected metadata.model to be present"
    );
}

#[then(expr = "the metadata extra should contain key {string}")]
fn then_metadata_extra_contains(world: &mut MiddensWorld, key: String) {
    let session = &world.sessions[0];
    assert!(
        session.metadata.extra.contains_key(&key),
        "expected metadata.extra to contain key '{key}'"
    );
}

// ---------------------------------------------------------------------------
// Then steps — messages
// ---------------------------------------------------------------------------

#[then(expr = "the session should have at least {int} user message(s)")]
fn then_min_user_messages(world: &mut MiddensWorld, min: usize) {
    let session = &world.sessions[0];
    assert!(
        session.user_message_count() >= min,
        "expected at least {} user message(s), got {}",
        min,
        session.user_message_count()
    );
}

#[then(expr = "the session should have at least {int} assistant message(s)")]
fn then_min_assistant_messages(world: &mut MiddensWorld, min: usize) {
    let session = &world.sessions[0];
    assert!(
        session.assistant_message_count() >= min,
        "expected at least {} assistant message(s), got {}",
        min,
        session.assistant_message_count()
    );
}

#[then(expr = "the session should have at least {int} thinking block(s)")]
fn then_min_thinking_blocks(world: &mut MiddensWorld, min: usize) {
    let session = &world.sessions[0];
    assert!(
        session.thinking_count() >= min,
        "expected at least {} thinking block(s), got {}",
        min,
        session.thinking_count()
    );
}

#[then(expr = "the session should have at least {int} tool call(s)")]
fn then_min_tool_calls(world: &mut MiddensWorld, min: usize) {
    let session = &world.sessions[0];
    assert!(
        session.total_tool_calls() >= min,
        "expected at least {} tool call(s), got {}",
        min,
        session.total_tool_calls()
    );
}

#[then(expr = "the tool sequence should contain {string}")]
fn then_tool_sequence_contains(world: &mut MiddensWorld, tool_name: String) {
    let session = &world.sessions[0];
    let names: Vec<&str> = session.tool_sequence();
    assert!(
        names.contains(&tool_name.as_str()),
        "expected tool sequence to contain '{tool_name}', got: {:?}",
        names
    );
}

#[then("at least one message should have tool results")]
fn then_has_tool_results(world: &mut MiddensWorld) {
    let session = &world.sessions[0];
    let has = session.messages.iter().any(|m| !m.tool_results.is_empty());
    assert!(has, "expected at least one message with tool results");
}

#[then(expr = "all messages should have role {string} or {string}")]
fn then_all_messages_roles(world: &mut MiddensWorld, role_a: String, role_b: String) {
    let session = &world.sessions[0];
    for msg in &session.messages {
        let actual = format!("{:?}", msg.role);
        assert!(
            actual == role_a || actual == role_b,
            "unexpected message role: {actual}, expected {role_a} or {role_b}"
        );
    }
}

// ---------------------------------------------------------------------------
// Then steps — path component check
// ---------------------------------------------------------------------------

#[then(expr = "the path should contain the {string} component")]
fn then_path_contains_component(world: &mut MiddensWorld, component: String) {
    let path = world.file_path.as_ref().expect("file_path not set");
    let has = path
        .components()
        .any(|c| c.as_os_str() == component.as_str());
    assert!(
        has,
        "expected path '{}' to contain component '{component}'",
        path.display()
    );
}

// ---------------------------------------------------------------------------
// Then steps — environment fingerprint
// ---------------------------------------------------------------------------

#[then(expr = "the environment tool version should be {string}")]
fn then_env_tool_version(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(
        session.environment.tool_version.as_deref(),
        Some(expected.as_str())
    );
}

#[then(expr = "the environment model id should be {string}")]
fn then_env_model_id(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(
        session.environment.model_id.as_deref(),
        Some(expected.as_str())
    );
}

#[then(expr = "the environment permission mode should be {string}")]
fn then_env_permission_mode(world: &mut MiddensWorld, expected: String) {
    let session = &world.sessions[0];
    assert_eq!(
        session.environment.permission_mode.as_deref(),
        Some(expected.as_str())
    );
}

// ---------------------------------------------------------------------------
// Then steps — auto-detect format
// ---------------------------------------------------------------------------

#[then(expr = "the detected format should be {string}")]
fn then_detected_format(world: &mut MiddensWorld, expected: String) {
    let format = world.detected_format.expect("detected_format not set");
    let actual = format!("{:?}", format);
    assert_eq!(actual, expected, "detected format mismatch");
}

#[then("no format should be detected")]
fn then_no_format(world: &mut MiddensWorld) {
    assert!(
        world.detected_format.is_none(),
        "expected no format to be detected, got {:?}",
        world.detected_format
    );
}
