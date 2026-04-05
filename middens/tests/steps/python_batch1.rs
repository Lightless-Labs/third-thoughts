use crate::steps::world::MiddensWorld;
use cucumber::{given, when, then};
use middens::bridge::technique::PythonTechnique;
use middens::bridge::uv::UvManager;
use middens::session::{
    EnvironmentFingerprint, Message, MessageClassification, MessageRole,
    Session, SessionMetadata, SessionType, SourceTool, ToolCall, ToolResult,
};
use middens::techniques::Technique;
use serde_json::json;
use std::path::PathBuf;

fn resolve_python_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let reqs = manifest_dir.join("python/requirements.txt");
    match UvManager::detect(reqs) {
        Ok(uv) => {
            if let Err(e) = uv.init() {
                eprintln!("uv init failed, falling back to python3: {}", e);
                return PathBuf::from("python3");
            }
            uv.python_path().clone()
        }
        Err(_) => PathBuf::from("python3"),
    }
}

fn technique_script_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("python/techniques")
        .join(format!("{}.py", name))
}

fn make_tool_call(turn: usize) -> ToolCall {
    let tools = ["Read", "Edit", "Bash", "Glob", "Grep"];
    let name = tools[turn % tools.len()];
    let dirs = ["src/", "src/parser/", "src/bridge/", "tests/", "python/"];
    let dir = dirs[turn % dirs.len()];
    ToolCall {
        id: format!("call_{}", turn),
        name: name.to_string(),
        input: json!({"path": format!("{}file_{}.rs", dir, turn)}),
    }
}

fn make_tool_result(call_id: &str, is_error: bool) -> ToolResult {
    ToolResult {
        tool_use_id: call_id.to_string(),
        content: if is_error { "Error: command failed".to_string() } else { "ok".to_string() },
        is_error,
    }
}

fn make_message(role: MessageRole, turn: usize, is_correction: bool) -> Message {
    let text = match role {
        MessageRole::User => format!("User message at turn {}", turn),
        MessageRole::Assistant => format!("Assistant response at turn {} with analysis and code changes", turn),
        _ => format!("System message {}", turn),
    };

    let (tool_calls, tool_results, thinking) = if role == MessageRole::Assistant {
        let tc = make_tool_call(turn);
        let tr = make_tool_result(&tc.id, turn % 7 == 0); // occasional failure
        (
            vec![tc],
            vec![tr],
            Some(format!("Thinking about turn {}. Let me analyze the code and decide on the best approach.", turn)),
        )
    } else {
        (vec![], vec![], None)
    };

    let classification = if role == MessageRole::User {
        if is_correction {
            MessageClassification::HumanCorrection
        } else if turn == 0 {
            MessageClassification::HumanDirective
        } else {
            MessageClassification::Unclassified
        }
    } else {
        MessageClassification::Unclassified
    };

    Message {
        role,
        timestamp: None,
        text,
        thinking,
        tool_calls,
        tool_results,
        classification,
        raw_content: vec![],
    }
}

fn create_session(id: &str, num_turns: usize, high_correction: bool) -> Session {
    let mut messages = Vec::new();
    for i in 0..num_turns {
        let is_correction = if high_correction { i % 3 == 0 && i > 0 } else { i % 7 == 0 && i > 2 };
        messages.push(make_message(MessageRole::User, i, is_correction));
        messages.push(make_message(MessageRole::Assistant, i, false));
    }
    Session {
        id: id.to_string(),
        source_path: PathBuf::from(format!("{}.jsonl", id)),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages,
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
    }
}

// ── Background steps ──

#[given("a set of Python techniques")]
fn given_python_techniques(_world: &mut MiddensWorld) {
    // Existence check — scripts will be validated when run
}

#[given("a resolver for the Python executable")]
fn given_python_resolver(_world: &mut MiddensWorld) {
    // resolve_python_path() is called at run time
}

// ── Fixture data steps ──

#[given(expr = "a set of {int} sessions, each with {int}-{int} turns, including thinking and tool use")]
fn given_sessions_with_turns(world: &mut MiddensWorld, count: i32, min: i32, max: i32) {
    world.sessions = (0..count)
        .map(|i| {
            let turns = (min as usize) + (i as usize % ((max - min + 1) as usize));
            create_session(&format!("session_{}", i), turns, false)
        })
        .collect();
}

#[given(expr = "a set of {int} sessions with a mix of high and low correction rates, tool calls, and thinking")]
fn given_mixed_sessions(world: &mut MiddensWorld, count: i32) {
    world.sessions = (0..count)
        .map(|i| {
            let turns = 15 + (i as usize % 20);
            create_session(&format!("session_{}", i), turns, i % 2 == 0)
        })
        .collect();
}

#[given(expr = "a set of {int} sessions, each with more than {int} turns")]
fn given_long_sessions(world: &mut MiddensWorld, count: i32, min_turns: i32) {
    world.sessions = (0..count)
        .map(|i| {
            let turns = (min_turns as usize) + 1 + (i as usize % 15);
            create_session(&format!("session_{}", i), turns, false)
        })
        .collect();
}

#[given(expr = "a set of {int} sessions, {int} with less than {int} turns and {int} with more")]
fn given_mixed_length_sessions(world: &mut MiddensWorld, _total: i32, short: i32, threshold: i32, long: i32) {
    let mut sessions = Vec::new();
    for i in 0..short {
        let turns = 5 + (i as usize % ((threshold as usize).saturating_sub(6)));
        sessions.push(create_session(&format!("short_{}", i), turns, false));
    }
    for i in 0..long {
        let turns = (threshold as usize) + 1 + (i as usize % 10);
        sessions.push(create_session(&format!("long_{}", i), turns, false));
    }
    world.sessions = sessions;
}

#[given(expr = "a set of {int} varied sessions")]
fn given_varied_sessions(world: &mut MiddensWorld, count: i32) {
    world.sessions = (0..count)
        .map(|i| {
            let turns = 5 + (i as usize % 35);
            create_session(&format!("varied_{}", i), turns, i % 3 == 0)
        })
        .collect();
}

#[given("an empty array of sessions")]
fn given_empty_sessions(world: &mut MiddensWorld) {
    world.sessions = Vec::new();
}

#[given("an invalid session file path")]
fn given_invalid_path(world: &mut MiddensWorld) {
    if world.temp_dir.is_none() {
        world.temp_dir = Some(tempfile::tempdir().unwrap());
    }
    world.file_path = Some(
        world.temp_dir.as_ref().unwrap().path().join("nonexistent_sessions.json"),
    );
}

// ── Execution steps ──

#[when(expr = "the {string} technique is run")]
fn when_technique_is_run(world: &mut MiddensWorld, name: String) {
    let python_path = resolve_python_path();
    let script_path = technique_script_path(&name);
    let tech = PythonTechnique::new(&name, &format!("{} analysis", name), script_path, python_path, 120);

    match tech.run(&world.sessions) {
        Ok(res) => world.technique_result = Some(res),
        Err(e) => world.error = Some(e.to_string()),
    }
}

#[when(expr = "I attempt to run the {string} technique with the invalid path")]
fn when_run_with_invalid_path(world: &mut MiddensWorld, name: String) {
    let python_path = resolve_python_path();
    let script_path = technique_script_path(&name);
    let invalid_arg = world.file_path.as_ref().expect("No file path set");

    let output = std::process::Command::new(&python_path)
        .arg(&script_path)
        .arg(invalid_arg)
        .output()
        .expect("Failed to execute Python process");

    world.cli_exit_code = output.status.code();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    if !output.status.success() {
        world.error = Some(format!("Exit code: {:?}, Stderr: {}", world.cli_exit_code, world.cli_stderr));
    }
}

// ── Assertion steps ──

#[then("the technique should succeed")]
fn then_technique_succeeds(world: &mut MiddensWorld) {
    assert!(world.error.is_none(), "Technique failed: {:?}", world.error);
    assert!(world.technique_result.is_some(), "No TechniqueResult produced");
}

#[then(expr = "the result summary should mention {string}")]
fn then_summary_mentions(world: &mut MiddensWorld, keyword: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert!(
        result.summary.to_lowercase().contains(&keyword.to_lowercase()),
        "Summary does not contain '{}': {}", keyword, result.summary,
    );
}

#[then(expr = "the result summary should contain {string}")]
fn then_summary_contains(world: &mut MiddensWorld, text: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert!(
        result.summary.to_lowercase().contains(&text.to_lowercase()),
        "Summary does not contain '{}': {}", text, result.summary,
    );
}

#[then(expr = "the result summary should mention {string} and {string}")]
fn then_summary_mentions_two(world: &mut MiddensWorld, kw1: String, kw2: String) {
    let result = world.technique_result.as_ref().expect("No result");
    let summary_lower = result.summary.to_lowercase();
    assert!(summary_lower.contains(&kw1.to_lowercase()), "Summary missing '{}': {}", kw1, result.summary);
    assert!(summary_lower.contains(&kw2.to_lowercase()), "Summary missing '{}': {}", kw2, result.summary);
}

#[then(expr = "the result should have a numeric finding with label {string}")]
fn then_has_numeric_finding(world: &mut MiddensWorld, label: String) {
    let result = world.technique_result.as_ref().expect("No result");
    let finding = result.findings.iter().find(|f| f.label == label)
        .unwrap_or_else(|| panic!("Finding '{}' not found in: {:?}", label, result.findings.iter().map(|f| &f.label).collect::<Vec<_>>()));
    assert!(finding.value.is_number(), "Finding '{}' is not numeric: {:?}", label, finding.value);
}

#[then(expr = "the result should have a string finding with label {string}")]
fn then_has_string_finding(world: &mut MiddensWorld, label: String) {
    let result = world.technique_result.as_ref().expect("No result");
    let finding = result.findings.iter().find(|f| f.label == label)
        .unwrap_or_else(|| panic!("Finding '{}' not found", label));
    assert!(finding.value.is_string(), "Finding '{}' is not a string: {:?}", label, finding.value);
}

#[then(expr = "the result should have a finding with label {string}")]
fn then_has_finding(world: &mut MiddensWorld, label: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert!(
        result.findings.iter().any(|f| f.label == label),
        "Finding '{}' not found in: {:?}", label, result.findings.iter().map(|f| &f.label).collect::<Vec<_>>(),
    );
}

#[then(expr = "the result should have findings for {string} and {string}")]
fn then_has_two_findings(world: &mut MiddensWorld, label1: String, label2: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert!(result.findings.iter().any(|f| f.label == label1), "Finding '{}' not found", label1);
    assert!(result.findings.iter().any(|f| f.label == label2), "Finding '{}' not found", label2);
}

#[then(expr = "the result should contain a table named {string}")]
fn then_has_table(world: &mut MiddensWorld, name: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert!(
        result.tables.iter().any(|t| t.name == name),
        "Table '{}' not found in: {:?}", name, result.tables.iter().map(|t| &t.name).collect::<Vec<_>>(),
    );
}

#[then(expr = "the result summary should state that {int} sessions were skipped due to insufficient turns")]
fn then_summary_skipped(world: &mut MiddensWorld, count: i32) {
    let result = world.technique_result.as_ref().expect("No result");
    let summary_lower = result.summary.to_lowercase();
    assert!(
        summary_lower.contains(&format!("skipped {}", count)) || summary_lower.contains(&format!("{} skipped", count)),
        "Summary does not mention {} skipped sessions: {}", count, result.summary,
    );
}

#[then(expr = "the result should contain {int} findings")]
fn then_has_n_findings(world: &mut MiddensWorld, count: i32) {
    let result = world.technique_result.as_ref().expect("No result");
    assert_eq!(result.findings.len(), count as usize, "Expected {} findings, got {}", count, result.findings.len());
}

#[then("the result summary should indicate that 0 sessions were analyzed")]
fn then_summary_zero(world: &mut MiddensWorld) {
    let result = world.technique_result.as_ref().expect("No result");
    let s = result.summary.to_lowercase();
    assert!(
        s.contains("0 session") || s.contains("no session") || s.contains("empty"),
        "Summary doesn't indicate 0 sessions: {}", result.summary,
    );
}

#[then(expr = "the result name should be {string}")]
fn then_result_name(world: &mut MiddensWorld, name: String) {
    let result = world.technique_result.as_ref().expect("No result");
    assert_eq!(result.name, name);
}

#[then("the technique should fail with a non-zero exit code")]
fn then_technique_fails(world: &mut MiddensWorld) {
    assert!(world.error.is_some(), "Expected failure but technique succeeded");
    if let Some(code) = world.cli_exit_code {
        assert_ne!(code, 0, "Exit code should be non-zero");
    }
}

#[then("the captured stderr should not be empty")]
fn then_stderr_not_empty(world: &mut MiddensWorld) {
    assert!(!world.cli_stderr.is_empty(), "Expected stderr output but it was empty");
}

#[given(expr = "a set of {int} sessions with no tool calls")]
fn given_sessions_no_tool_calls(world: &mut MiddensWorld, count: i32) {
    world.sessions = (0..count)
        .map(|i| {
            let mut session = create_session(&format!("no_tools_{}", i), 10, false);
            for msg in &mut session.messages {
                msg.tool_calls.clear();
                msg.tool_results.clear();
            }
            session
        })
        .collect();
}
