use std::path::PathBuf;

use cucumber::{given, then, when};
use serde_json::json;
use sha2::{Digest, Sha256};

use middens::session::{
    EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session, SessionMetadata,
    SessionType, SourceTool, ToolCall,
};
use middens::techniques::burstiness::Burstiness;
use middens::techniques::correction_rate::CorrectionRate;
use middens::techniques::diversity::Diversity;
use middens::techniques::entropy::EntropyRate;
use middens::techniques::markov::MarkovChain;
use middens::techniques::{Technique, all_techniques};

use super::world::MiddensWorld;

// ---------------------------------------------------------------------------
// Helper: build a Session whose tool_sequence() returns the given tool names.
//
// Each tool call is placed in a single assistant message so that
// `session.tool_sequence()` yields the full list in order.
// ---------------------------------------------------------------------------
fn session_with_tools(id: &str, tool_names: &[&str]) -> Session {
    let messages = if tool_names.is_empty() {
        vec![]
    } else {
        vec![Message {
            role: MessageRole::Assistant,
            timestamp: None,
            text: String::new(),
            thinking: None,
            tool_calls: tool_names
                .iter()
                .map(|name| ToolCall {
                    id: format!("call_{}", name),
                    name: name.to_string(),
                    input: serde_json::Value::Null,
                })
                .collect(),
            tool_results: vec![],
            classification: MessageClassification::Other,
            raw_content: vec![],
        }]
    };

    Session {
        id: id.to_string(),
        source_path: PathBuf::from("/tmp/test.jsonl"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages,
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Unknown,
    }
}

fn expected_project_label(project: &str) -> String {
    if project == "unknown"
        || matches!(
            std::env::var("MIDDENS_INCLUDE_PROJECT_NAMES").as_deref(),
            Ok("1")
        )
    {
        project.to_string()
    } else {
        let mut hasher = Sha256::new();
        hasher.update(project.as_bytes());
        let hash = format!("{:x}", hasher.finalize());
        format!("project_{}", &hash[..8])
    }
}

// ---------------------------------------------------------------------------
// Helper: build a Session with one-tool-per-message layout (for burstiness,
// where position within the flat sequence matters).
// ---------------------------------------------------------------------------
fn session_with_tools_per_message(id: &str, tool_names: &[&str]) -> Session {
    let messages = tool_names
        .iter()
        .map(|name| Message {
            role: MessageRole::Assistant,
            timestamp: None,
            text: String::new(),
            thinking: None,
            tool_calls: vec![ToolCall {
                id: String::new(),
                name: name.to_string(),
                input: serde_json::Value::Null,
            }],
            tool_results: vec![],
            classification: MessageClassification::Other,
            raw_content: vec![],
        })
        .collect();

    Session {
        id: id.to_string(),
        source_path: PathBuf::from("/tmp/test.jsonl"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages,
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Unknown,
    }
}

// ---------------------------------------------------------------------------
// Helper: build a Session with user messages carrying specific classifications.
// Each user message is followed by an assistant message.
// ---------------------------------------------------------------------------
fn session_with_classifications(
    id: &str,
    classifications: &[MessageClassification],
    project: Option<&str>,
) -> Session {
    let mut messages = Vec::new();
    for c in classifications {
        messages.push(Message {
            role: MessageRole::User,
            timestamp: None,
            text: "test".to_string(),
            thinking: None,
            tool_calls: vec![],
            tool_results: vec![],
            classification: *c,
            raw_content: vec![],
        });
        messages.push(Message {
            role: MessageRole::Assistant,
            timestamp: None,
            text: "response".to_string(),
            thinking: None,
            tool_calls: vec![],
            tool_results: vec![],
            classification: MessageClassification::Other,
            raw_content: vec![],
        });
    }

    Session {
        id: id.to_string(),
        source_path: PathBuf::from("/test"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages,
        metadata: SessionMetadata {
            project: project.map(|s| s.to_string()),
            ..Default::default()
        },
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Unknown,
    }
}

// ===========================================================================
//  GIVEN steps
// ===========================================================================

/// Parse a comma-separated tool list. Empty string yields an empty vec.
fn parse_tool_list(tools_csv: &str) -> Vec<String> {
    if tools_csv.is_empty() {
        return vec![];
    }
    tools_csv.split(',').map(|s| s.trim().to_string()).collect()
}

// -- Generic session construction -------------------------------------------

#[given(expr = "a session with tools {string}")]
fn given_session_with_tools(world: &mut MiddensWorld, tools_csv: String) {
    let names = parse_tool_list(&tools_csv);
    let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    world
        .sessions
        .push(session_with_tools("test-session", &refs));
}

#[given(expr = "no sessions")]
fn given_no_sessions(world: &mut MiddensWorld) {
    world.sessions.clear();
}

// -- Named session with tools (diversity, entropy) --------------------------

#[given(expr = "a session {string} with tools {string}")]
fn given_named_session_with_tools(world: &mut MiddensWorld, id: String, tools_csv: String) {
    let names = parse_tool_list(&tools_csv);
    let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    world.sessions.push(session_with_tools(&id, &refs));
}

// -- Entropy-specific session builders --------------------------------------

#[given(expr = "a session {string} with {int} repetitions of tools {string}")]
fn given_session_with_repetitions(
    world: &mut MiddensWorld,
    id: String,
    reps: usize,
    tools_csv: String,
) {
    let pattern = parse_tool_list(&tools_csv);
    let mut tools: Vec<String> = Vec::new();
    for _ in 0..reps {
        tools.extend(pattern.iter().cloned());
    }
    let refs: Vec<&str> = tools.iter().map(|s| s.as_str()).collect();
    world.sessions.push(session_with_tools(&id, &refs));
}

#[given(expr = "a session {string} with {int} copies of tool {string}")]
fn given_session_with_copies(world: &mut MiddensWorld, id: String, count: usize, tool: String) {
    let tools: Vec<&str> = vec![tool.as_str(); count];
    world.sessions.push(session_with_tools(&id, &tools));
}

#[given(expr = "a session {string} with an LCG tool sequence of length {int}")]
fn given_lcg_session(world: &mut MiddensWorld, id: String, length: usize) {
    let tool_names = ["Bash", "Read", "Edit", "Grep", "Write", "Glob"];
    let mut tools: Vec<&str> = Vec::new();
    let mut state: usize = 1;
    for _ in 0..length {
        state = (state * 13 + 7) % 97;
        tools.push(tool_names[state % tool_names.len()]);
    }
    world.sessions.push(session_with_tools(&id, &tools));
}

#[given(expr = "a deterministic sequence {string}")]
fn given_deterministic_sequence(world: &mut MiddensWorld, tools_csv: String) {
    // Store the sequence for conditional entropy computation in world.
    // We use numeric_result as a temporary holder -- the When step will compute.
    let names = parse_tool_list(&tools_csv);
    let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    // Store as a single session; the When step will use it directly.
    world.sessions.push(session_with_tools("det", &refs));
}

// -- Diversity-specific session builders ------------------------------------

#[given(expr = "a session {string} with {int} copies each of tools {string}")]
fn given_session_with_copies_each(
    world: &mut MiddensWorld,
    id: String,
    count: usize,
    tools_csv: String,
) {
    let pattern = parse_tool_list(&tools_csv);
    let mut tools: Vec<String> = Vec::new();
    for tool in &pattern {
        for _ in 0..count {
            tools.push(tool.clone());
        }
    }
    let refs: Vec<&str> = tools.iter().map(|s| s.as_str()).collect();
    world.sessions.push(session_with_tools(&id, &refs));
}

#[given(
    expr = "a session {string} with {int} copies of tool {string} and {int} copy of tool {string}"
)]
fn given_session_with_uneven_tools(
    world: &mut MiddensWorld,
    id: String,
    count1: usize,
    tool1: String,
    count2: usize,
    tool2: String,
) {
    let mut tool_strings: Vec<String> = vec![tool1; count1];
    tool_strings.extend(vec![tool2; count2]);
    let refs: Vec<&str> = tool_strings.iter().map(|s| s.as_str()).collect();
    world.sessions.push(session_with_tools(&id, &refs));
}

#[given(expr = "a species-area session {string} with {int} tools and {int} unique")]
fn given_species_area_session(world: &mut MiddensWorld, id: String, total: usize, unique: usize) {
    assert!(unique > 0, "unique must be > 0, got {unique}");
    assert!(
        unique <= total,
        "unique ({unique}) must be <= total ({total})"
    );
    // Build a session with `total` tool calls and `unique` distinct tool names.
    let unique_tools: Vec<String> = (0..unique).map(|i| format!("Tool{}", i)).collect();
    let mut tools: Vec<String> = Vec::new();
    // First, add one of each unique tool
    for t in &unique_tools {
        tools.push(t.clone());
    }
    // Fill the rest with the first tool
    while tools.len() < total {
        tools.push(unique_tools[0].clone());
    }
    let refs: Vec<&str> = tools.iter().map(|s| s.as_str()).collect();
    world.sessions.push(session_with_tools(&id, &refs));
}

// -- Burstiness-specific session builders -----------------------------------

#[given(expr = "a session with tool sequence {string}")]
fn given_session_with_tool_sequence(world: &mut MiddensWorld, tools_csv: String) {
    let names = parse_tool_list(&tools_csv);
    let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    world
        .sessions
        .push(session_with_tools_per_message("test", &refs));
}

#[given(
    expr = "a session with {int} periodic {string} tools interleaved with {string} and {int} clustered {string} tools"
)]
fn given_session_periodic_and_clustered(
    world: &mut MiddensWorld,
    periodic_count: usize,
    periodic_tool: String,
    filler_tool: String,
    clustered_count: usize,
    clustered_tool: String,
) {
    let mut tools: Vec<String> = Vec::new();
    for _ in 0..periodic_count {
        tools.push(periodic_tool.clone());
        tools.push(filler_tool.clone());
    }
    for _ in 0..clustered_count {
        tools.push(clustered_tool.clone());
    }
    let refs: Vec<&str> = tools.iter().map(|s| s.as_str()).collect();
    world
        .sessions
        .push(session_with_tools_per_message("test", &refs));
}

// -- Correction rate session builders ---------------------------------------

#[given(
    expr = "a session {string} in project {string} with {int} corrections and {int} directives"
)]
fn given_correction_session(
    world: &mut MiddensWorld,
    id: String,
    project: String,
    corrections: usize,
    directives: usize,
) {
    let mut classifications = vec![MessageClassification::HumanCorrection; corrections];
    classifications.extend(vec![MessageClassification::HumanDirective; directives]);
    world.sessions.push(session_with_classifications(
        &id,
        &classifications,
        Some(&project),
    ));
}

#[given(expr = "a session {string} with {int} directives then {int} corrections")]
fn given_session_directives_then_corrections(
    world: &mut MiddensWorld,
    id: String,
    directives: usize,
    corrections: usize,
) {
    let mut classifications = vec![MessageClassification::HumanDirective; directives];
    classifications.extend(vec![MessageClassification::HumanCorrection; corrections]);
    world
        .sessions
        .push(session_with_classifications(&id, &classifications, None));
}

#[given(expr = "an empty session {string}")]
fn given_empty_session(world: &mut MiddensWorld, id: String) {
    world.sessions.push(Session {
        id,
        source_path: PathBuf::from("/test"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages: vec![],
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Unknown,
    });
}

#[given(expr = "a session {string} with no project and {int} directives")]
fn given_session_no_project(world: &mut MiddensWorld, id: String, directives: usize) {
    let classifications = vec![MessageClassification::HumanDirective; directives];
    world
        .sessions
        .push(session_with_classifications(&id, &classifications, None));
}

// ===========================================================================
//  WHEN steps
// ===========================================================================

#[when("I run the markov technique")]
fn when_run_markov(world: &mut MiddensWorld) {
    let technique = MarkovChain;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I run the entropy technique")]
fn when_run_entropy(world: &mut MiddensWorld) {
    let technique = EntropyRate;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I run the entropy technique on the session")]
fn when_run_entropy_on_session(world: &mut MiddensWorld) {
    let technique = EntropyRate;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I run the diversity technique")]
fn when_run_diversity(world: &mut MiddensWorld) {
    let technique = Diversity;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I compute diversity metrics for the session")]
fn when_compute_diversity_metrics(world: &mut MiddensWorld) {
    // Run the diversity technique on just the sessions in the world.
    let technique = Diversity;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I compute the species-area curve")]
fn when_compute_species_area(world: &mut MiddensWorld) {
    let technique = Diversity;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I run the burstiness technique")]
fn when_run_burstiness(world: &mut MiddensWorld) {
    let technique = Burstiness;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I run the correction rate technique")]
fn when_run_correction_rate(world: &mut MiddensWorld) {
    let technique = CorrectionRate;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[when("I list all registered techniques")]
fn when_list_techniques(world: &mut MiddensWorld) {
    let techniques = all_techniques();
    // Store the technique names in cli_output for assertion.
    world.cli_output = techniques
        .iter()
        .map(|t| t.name().to_string())
        .collect::<Vec<_>>()
        .join(",");
}

// ===========================================================================
//  THEN steps
// ===========================================================================

// -- Generic finding assertions ---------------------------------------------

#[then(expr = "finding {string} should be integer {int}")]
fn then_finding_integer(world: &mut MiddensWorld, label: String, expected: i64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == label)
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    assert_eq!(
        finding.value,
        json!(expected),
        "finding '{}': expected {}, got {}",
        label,
        expected,
        finding.value
    );
}

#[then(expr = "finding {string} should be float {float}")]
fn then_finding_float(world: &mut MiddensWorld, label: String, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == label)
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    assert_eq!(
        finding.value,
        json!(expected),
        "finding '{}': expected {}, got {}",
        label,
        expected,
        finding.value
    );
}

#[then(expr = "finding {string} should be approximately {float}")]
fn then_finding_approximately(world: &mut MiddensWorld, label: String, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == label)
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    let actual: f64 = serde_json::from_value(finding.value.clone())
        .unwrap_or_else(|_| panic!("finding '{}' is not a number: {}", label, finding.value));
    assert!(
        (actual - expected).abs() < 1e-9,
        "finding '{}': expected ~{}, got {}",
        label,
        expected,
        actual
    );
}

#[then(expr = "finding {string} should be a negative number")]
fn then_finding_negative(world: &mut MiddensWorld, label: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == label)
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    let val = finding.value.as_f64().expect("finding is not a number");
    assert!(
        val < 0.0,
        "finding '{}': expected negative, got {}",
        label,
        val
    );
}

// -- Table assertions -------------------------------------------------------

#[then(expr = "the technique result should have a table {string}")]
fn then_result_has_table(world: &mut MiddensWorld, table_name: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    assert!(
        result.tables.iter().any(|t| t.name == table_name),
        "table '{}' not found in result",
        table_name
    );
}

#[then(expr = "the technique result should have {int} tables")]
fn then_result_table_count(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    assert_eq!(
        result.tables.len(),
        expected,
        "expected {} tables, got {}",
        expected,
        result.tables.len()
    );
}

#[then(expr = "the technique result should have a table {string} with {int} rows")]
fn then_result_table_with_rows(world: &mut MiddensWorld, table_name: String, expected_rows: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == table_name)
        .unwrap_or_else(|| panic!("table '{}' not found", table_name));
    assert_eq!(
        table.rows.len(),
        expected_rows,
        "table '{}': expected {} rows, got {}",
        table_name,
        expected_rows,
        table.rows.len()
    );
}

// -- Markov transition matrix assertions ------------------------------------

#[then(expr = "the transition matrix should have {int} columns")]
fn then_transition_matrix_columns(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "transition_matrix")
        .expect("transition_matrix table missing");
    assert_eq!(
        table.columns.len(),
        expected,
        "expected {} columns, got {}",
        expected,
        table.columns.len()
    );
}

#[then(expr = "the transition from {string} to {string} should be {float}")]
fn then_transition_value(
    world: &mut MiddensWorld,
    from_tool: String,
    to_tool: String,
    expected: f64,
) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "transition_matrix")
        .expect("transition_matrix table missing");

    let to_col = table
        .columns
        .iter()
        .position(|c| c == &to_tool)
        .unwrap_or_else(|| panic!("column '{}' not found", to_tool));

    let row = table
        .rows
        .iter()
        .find(|r| r[0] == json!(from_tool.as_str()))
        .unwrap_or_else(|| panic!("row for '{}' not found", from_tool));

    assert_eq!(
        row[to_col],
        json!(expected),
        "transition {} -> {}: expected {}, got {}",
        from_tool,
        to_tool,
        expected,
        row[to_col]
    );
}

// -- Markov stationary distribution -----------------------------------------

#[then("the stationary distribution should sum to approximately 1.0")]
fn then_stationary_sums_to_one(world: &mut MiddensWorld) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let stationary_sum: f64 = result
        .findings
        .iter()
        .filter(|f| f.label.starts_with("stationary_"))
        .map(|f| f.value.as_f64().unwrap())
        .sum();
    assert!(
        (stationary_sum - 1.0).abs() < 1e-4,
        "Stationary distribution should sum to ~1.0, got {}",
        stationary_sum
    );
}

// -- Entropy per-session assertions -----------------------------------------

#[then(expr = "the session entropy mean should be less than {float}")]
fn then_session_entropy_mean_less_than(world: &mut MiddensWorld, threshold: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    // Get mean_entropy from the per_session_entropy table (first row).
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_entropy")
        .expect("per_session_entropy table missing");
    assert!(
        !table.rows.is_empty(),
        "per_session_entropy table has no rows"
    );
    // mean_entropy is column index 1
    let mean = table.rows[0][1]
        .as_f64()
        .expect("mean_entropy is not a number");
    assert!(
        mean < threshold,
        "session mean entropy {} should be less than {}",
        mean,
        threshold
    );
}

#[then(expr = "the session entropy mean should be greater than {float}")]
fn then_session_entropy_mean_greater_than(world: &mut MiddensWorld, threshold: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_entropy")
        .expect("per_session_entropy table missing");
    assert!(
        !table.rows.is_empty(),
        "per_session_entropy table has no rows"
    );
    let mean = table.rows[0][1]
        .as_f64()
        .expect("mean_entropy is not a number");
    assert!(
        mean > threshold,
        "session mean entropy {} should be greater than {}",
        mean,
        threshold
    );
}

#[then("the session entropy result should be none")]
fn then_session_entropy_result_none(world: &mut MiddensWorld) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let analyzed = result
        .findings
        .iter()
        .find(|f| f.label == "sessions_analyzed")
        .unwrap();
    assert_eq!(
        analyzed.value,
        json!(0),
        "expected 0 sessions analyzed (session too short)"
    );
}

#[then(expr = "the session entropy anomaly count should be {int}")]
fn then_session_entropy_anomaly_count(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_entropy")
        .expect("per_session_entropy table missing");
    assert!(
        !table.rows.is_empty(),
        "per_session_entropy table has no rows"
    );
    // num_anomalies is column index 3
    let anomalies = table.rows[0][3]
        .as_u64()
        .expect("num_anomalies is not a number") as usize;
    assert_eq!(
        anomalies, expected,
        "expected {} anomalies, got {}",
        expected, anomalies
    );
}

// -- Conditional entropy numeric result -------------------------------------

#[then(expr = "the numeric result should be less than {float}")]
fn then_numeric_result_less_than(world: &mut MiddensWorld, threshold: f64) {
    let val = world.numeric_result.expect("no numeric result");
    assert!(
        val < threshold,
        "numeric result {} should be less than {}",
        val,
        threshold
    );
}

// -- Diversity per-session assertions ---------------------------------------

#[then(expr = "the session richness should be {int}")]
fn then_session_richness(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    // richness is column index 4
    let richness = table.rows[0][4].as_u64().unwrap() as usize;
    assert_eq!(richness, expected);
}

#[then(expr = "the session abundance should be {int}")]
fn then_session_abundance(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    // abundance is column index 5
    let abundance = table.rows[0][5].as_u64().unwrap() as usize;
    assert_eq!(abundance, expected);
}

#[then(expr = "the session shannon should be approximately {float}")]
fn then_session_shannon_approx(world: &mut MiddensWorld, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    // shannon is column index 1
    let shannon = table.rows[0][1].as_f64().unwrap();
    assert!(
        (shannon - expected).abs() < 1e-10,
        "shannon: expected ~{}, got {}",
        expected,
        shannon
    );
}

#[then("the session shannon should be approximately ln4")]
fn then_session_shannon_ln4(world: &mut MiddensWorld) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    let shannon = table.rows[0][1].as_f64().unwrap();
    let expected = (4.0f64).ln();
    assert!(
        (shannon - expected).abs() < 1e-10,
        "shannon: expected ln(4)={}, got {}",
        expected,
        shannon
    );
}

#[then(expr = "the session simpson should be approximately {float}")]
fn then_session_simpson_approx(world: &mut MiddensWorld, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    // simpson is column index 2
    let simpson = table.rows[0][2].as_f64().unwrap();
    assert!(
        (simpson - expected).abs() < 1e-10,
        "simpson: expected ~{}, got {}",
        expected,
        simpson
    );
}

#[then(expr = "the session evenness should be approximately {float}")]
fn then_session_evenness_approx(world: &mut MiddensWorld, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session_diversity")
        .expect("per_session_diversity table missing");
    // evenness is column index 3
    let evenness = table.rows[0][3].as_f64().unwrap();
    assert!(
        (evenness - expected).abs() < 1e-10,
        "evenness: expected ~{}, got {}",
        expected,
        evenness
    );
}

// -- Species-area assertions ------------------------------------------------

#[then(expr = "the species-area z should be approximately {float} within {float}")]
fn then_species_area_z(world: &mut MiddensWorld, expected: f64, tolerance: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == "species_area_z")
        .expect("species_area_z finding missing");
    let z = finding.value.as_f64().unwrap();
    assert!(
        (z - expected).abs() < tolerance,
        "species-area z: expected ~{} (within {}), got {}",
        expected,
        tolerance,
        z
    );
}

#[then(expr = "the species-area r-squared should be greater than {float}")]
fn then_species_area_r_squared(world: &mut MiddensWorld, threshold: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == "species_area_r_squared")
        .expect("species_area_r_squared finding missing");
    let r2 = finding.value.as_f64().unwrap();
    assert!(
        r2 > threshold,
        "species-area R-squared {} should be > {}",
        r2,
        threshold
    );
}

// -- Diversity result assertions --------------------------------------------

#[then(expr = "the technique result name should be {string}")]
fn then_result_name(world: &mut MiddensWorld, expected: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    assert_eq!(result.name, expected);
}

#[then(expr = "the technique result should have findings {string}")]
fn then_result_has_findings(world: &mut MiddensWorld, labels_csv: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let expected_labels: Vec<&str> = labels_csv.split(',').collect();
    let actual_labels: Vec<&str> = result.findings.iter().map(|f| f.label.as_str()).collect();
    for label in &expected_labels {
        assert!(
            actual_labels.contains(label),
            "finding '{}' not found in {:?}",
            label,
            actual_labels
        );
    }
}

// -- Burstiness assertions --------------------------------------------------

fn find_burstiness_row<'a>(
    world: &'a MiddensWorld,
    tool_name: &str,
) -> Option<&'a Vec<serde_json::Value>> {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_tool_burstiness")
        .expect("per_tool_burstiness table missing");
    table.rows.iter().find(|r| r[0] == json!(tool_name))
}

#[then(expr = "tool {string} should have burstiness B close to {float} within {float}")]
fn then_tool_burstiness_close_to(
    world: &mut MiddensWorld,
    tool: String,
    expected: f64,
    tolerance: f64,
) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    let b = row[1].as_f64().unwrap();
    assert!(
        (b - expected).abs() < tolerance,
        "tool '{}' B: expected ~{} (within {}), got {}",
        tool,
        expected,
        tolerance,
        b
    );
}

#[then(expr = "tool {string} should have burstiness B greater than {float}")]
fn then_tool_burstiness_greater_than(world: &mut MiddensWorld, tool: String, threshold: f64) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    let b = row[1].as_f64().unwrap();
    assert!(
        b > threshold,
        "tool '{}' B: expected > {}, got {}",
        tool,
        threshold,
        b
    );
}

#[then(expr = "tool {string} should have burstiness B between {float} and {float}")]
fn then_tool_burstiness_between(world: &mut MiddensWorld, tool: String, low: f64, high: f64) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    let b = row[1].as_f64().unwrap();
    assert!(
        b > low && b < high,
        "tool '{}' B: expected between {} and {}, got {}",
        tool,
        low,
        high,
        b
    );
}

#[then(expr = "tool {string} should have a numeric burstiness B")]
fn then_tool_has_numeric_b(world: &mut MiddensWorld, tool: String) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    assert!(
        row[1].is_number(),
        "tool '{}' B should be a number, got {:?}",
        tool,
        row[1]
    );
}

#[then(expr = "tool {string} should have null memory M")]
fn then_tool_null_m(world: &mut MiddensWorld, tool: String) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    assert!(
        row[2].is_null(),
        "tool '{}' M should be null, got {:?}",
        tool,
        row[2]
    );
}

#[then(expr = "tool {string} should have a numeric memory M")]
fn then_tool_has_numeric_m(world: &mut MiddensWorld, tool: String) {
    let row = find_burstiness_row(world, &tool)
        .unwrap_or_else(|| panic!("tool '{}' not found in burstiness table", tool));
    assert!(
        row[2].is_number(),
        "tool '{}' M should be a number, got {:?}",
        tool,
        row[2]
    );
}

#[then(expr = "tool {string} should not appear in the burstiness table")]
fn then_tool_not_in_table(world: &mut MiddensWorld, tool: String) {
    let row = find_burstiness_row(world, &tool);
    assert!(
        row.is_none(),
        "tool '{}' should not appear in the burstiness table",
        tool
    );
}

// -- Correction rate assertions ---------------------------------------------

fn assert_per_session_table_row_count(world: &MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    assert_eq!(table.rows.len(), expected);
}

#[then(regex = r"^the per-session table should have (\d+) rows?$")]
fn then_per_session_table_rows(world: &mut MiddensWorld, expected: usize) {
    assert_per_session_table_row_count(world, expected);
}

#[then(expr = "the per-project table should have {int} rows")]
fn then_per_project_table_rows(world: &mut MiddensWorld, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    assert_eq!(table.rows.len(), expected);
}

#[then(expr = "per-session row {int} should have correction_rate approximately {float}")]
fn then_per_session_correction_rate(world: &mut MiddensWorld, row_idx: usize, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let cr: f64 = serde_json::from_value(table.rows[row_idx][1].clone()).unwrap();
    assert!(
        (cr - expected).abs() < 1e-9,
        "correction_rate: expected ~{}, got {}",
        expected,
        cr
    );
}

#[then(expr = "per-session row {int} should have {int} corrections")]
fn then_per_session_corrections(world: &mut MiddensWorld, row_idx: usize, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let corrections: usize = serde_json::from_value(table.rows[row_idx][5].clone()).unwrap();
    assert_eq!(corrections, expected);
}

#[then(expr = "per-session row {int} should have {int} user messages")]
fn then_per_session_user_messages(world: &mut MiddensWorld, row_idx: usize, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let user_messages: usize = serde_json::from_value(table.rows[row_idx][6].clone()).unwrap();
    assert_eq!(user_messages, expected);
}

#[then(expr = "per-session row {int} should have first_third_rate {float}")]
fn then_per_session_first_third_rate(world: &mut MiddensWorld, row_idx: usize, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let rate: f64 = serde_json::from_value(table.rows[row_idx][2].clone()).unwrap();
    assert!(
        (rate - expected).abs() < 1e-9,
        "first_third_rate: expected {}, got {}",
        expected,
        rate
    );
}

#[then(expr = "per-session row {int} should have last_third_rate {float}")]
fn then_per_session_last_third_rate(world: &mut MiddensWorld, row_idx: usize, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let rate: f64 = serde_json::from_value(table.rows[row_idx][3].clone()).unwrap();
    assert!(
        (rate - expected).abs() < 1e-9,
        "last_third_rate: expected {}, got {}",
        expected,
        rate
    );
}

#[then(expr = "per-session row {int} should have null degradation_ratio")]
fn then_per_session_null_degradation(world: &mut MiddensWorld, row_idx: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    assert!(
        table.rows[row_idx][4].is_null(),
        "degradation_ratio should be null, got {}",
        table.rows[row_idx][4]
    );
}

#[then(expr = "per-session row {int} should have degradation_ratio {float}")]
fn then_per_session_degradation_ratio(world: &mut MiddensWorld, row_idx: usize, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_session")
        .expect("per_session table missing");
    let degradation: f64 = serde_json::from_value(table.rows[row_idx][4].clone()).unwrap();
    assert!(
        (degradation - expected).abs() < 1e-9,
        "degradation_ratio: expected {}, got {}",
        expected,
        degradation
    );
}

#[then(expr = "the per-project table should have {int} row for project {string}")]
fn then_per_project_row_for(world: &mut MiddensWorld, expected_rows: usize, project: String) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    let project = expected_project_label(&project);
    let expected_project = json!(project.clone());
    let matching: Vec<_> = table
        .rows
        .iter()
        .filter(|r| r[0] == expected_project)
        .collect();
    assert_eq!(
        matching.len(),
        expected_rows,
        "expected {} rows for project '{}', found {}",
        expected_rows,
        project,
        matching.len()
    );
}

#[then(expr = "the per-project row for {string} should have correction_rate approximately {float}")]
fn then_per_project_correction_rate(world: &mut MiddensWorld, project: String, expected: f64) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    let project = expected_project_label(&project);
    let expected_project = json!(project.clone());
    let row = table
        .rows
        .iter()
        .find(|r| r[0] == expected_project)
        .unwrap_or_else(|| panic!("project '{}' not found", project));
    let rate: f64 = serde_json::from_value(row[1].clone()).unwrap();
    assert!(
        (rate - expected).abs() < 1e-9,
        "correction_rate for '{}': expected ~{}, got {}",
        project,
        expected,
        rate
    );
}

#[then(expr = "the per-project row for {string} should have {int} total corrections")]
fn then_per_project_total_corrections(world: &mut MiddensWorld, project: String, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    let project = expected_project_label(&project);
    let expected_project = json!(project.clone());
    let row = table
        .rows
        .iter()
        .find(|r| r[0] == expected_project)
        .unwrap();
    let corrections: usize = serde_json::from_value(row[2].clone()).unwrap();
    assert_eq!(corrections, expected);
}

#[then(expr = "the per-project row for {string} should have {int} total user messages")]
fn then_per_project_total_user_messages(
    world: &mut MiddensWorld,
    project: String,
    expected: usize,
) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    let project = expected_project_label(&project);
    let expected_project = json!(project.clone());
    let row = table
        .rows
        .iter()
        .find(|r| r[0] == expected_project)
        .unwrap();
    let user_messages: usize = serde_json::from_value(row[3].clone()).unwrap();
    assert_eq!(user_messages, expected);
}

#[then(expr = "the per-project row for {string} should have {int} sessions")]
fn then_per_project_session_count(world: &mut MiddensWorld, project: String, expected: usize) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let table = result
        .tables
        .iter()
        .find(|t| t.name == "per_project")
        .expect("per_project table missing");
    let project = expected_project_label(&project);
    let expected_project = json!(project.clone());
    let row = table
        .rows
        .iter()
        .find(|r| r[0] == expected_project)
        .unwrap();
    let session_count: usize = serde_json::from_value(row[4].clone()).unwrap();
    assert_eq!(session_count, expected);
}

// -- Registry assertions ----------------------------------------------------

#[then("the technique list should not be empty")]
fn then_technique_list_not_empty(world: &mut MiddensWorld) {
    assert!(
        !world.cli_output.is_empty(),
        "technique list should not be empty"
    );
}

#[then(expr = "the technique list should contain {string}")]
fn then_technique_list_contains(world: &mut MiddensWorld, name: String) {
    let names: Vec<&str> = world.cli_output.split(',').collect();
    assert!(
        names.contains(&name.as_str()),
        "technique list {:?} should contain '{}'",
        names,
        name
    );
}
