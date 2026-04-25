use std::collections::BTreeMap;
use std::path::PathBuf;

use cucumber::{given, then, when};
use serde_json::json;

use middens::output::OutputMetadata;
use middens::output::ascii::{render_ascii_bar, render_ascii_sparkline, render_ascii_table};
use middens::output::json::render_json;
use middens::output::markdown::render_markdown;
use middens::session::{
    EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session, SessionMetadata,
    SessionType, SourceTool, ToolCall,
};
use middens::techniques::{DataTable, FigureKind, FigureSpec, Finding, TechniqueResult};

use super::world::MiddensWorld;

// ===========================================================================
// State encoding helpers
//
// We store all output-engine state in existing MiddensWorld fields to avoid
// thread-local storage (which breaks under cucumber-rs's concurrent execution).
//
// Field mapping:
//   cli_output  – primary rendered string (markdown, sparkline, bar, ascii table)
//   cli_stderr  – secondary rendered string (JSON serialized, or integration JSON)
//   error       – serialized auxiliary input state (metadata JSON, sparkline
//                 values JSON, bar params JSON)
//   file_path   – used as a flag/secondary storage when needed
// ===========================================================================

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn default_metadata() -> OutputMetadata {
    OutputMetadata {
        technique_name: "test".to_string(),
        corpus_size: 100,
        generated_at: "2026-01-01T00:00:00Z".to_string(),
        middens_version: "0.1.0".to_string(),
        parameters: BTreeMap::new(),
    }
}

fn empty_result(name: &str) -> TechniqueResult {
    TechniqueResult {
        name: name.to_string(),
        summary: String::new(),
        findings: vec![],
        tables: vec![],
        figures: vec![],
    }
}

fn make_data_table(name: &str, columns: &[&str], num_rows: usize) -> DataTable {
    let cols: Vec<String> = columns.iter().map(|c| c.to_string()).collect();
    let rows: Vec<Vec<serde_json::Value>> = (0..num_rows)
        .map(|i| {
            cols.iter()
                .enumerate()
                .map(|(ci, _)| json!(format!("r{}c{}", i, ci)))
                .collect()
        })
        .collect();
    DataTable {
        name: name.to_string(),
        columns: cols,
        rows,
        column_types: None,
    }
}

fn get_technique_result(world: &MiddensWorld) -> TechniqueResult {
    world
        .technique_result
        .clone()
        .expect("technique_result must be set before rendering")
}

/// Serialize OutputMetadata to JSON string for storage in world.error.
fn serialize_metadata(meta: &OutputMetadata) -> String {
    let params: serde_json::Value = json!(meta.parameters);
    json!({
        "technique_name": meta.technique_name,
        "corpus_size": meta.corpus_size,
        "generated_at": meta.generated_at,
        "middens_version": meta.middens_version,
        "parameters": params,
    })
    .to_string()
}

/// Deserialize OutputMetadata from JSON string stored in world.error.
fn deserialize_metadata(s: &str) -> OutputMetadata {
    let v: serde_json::Value = serde_json::from_str(s).expect("invalid metadata JSON");
    let params: BTreeMap<String, String> = v
        .get("parameters")
        .and_then(|p| serde_json::from_value(p.clone()).ok())
        .unwrap_or_default();
    OutputMetadata {
        technique_name: v["technique_name"].as_str().unwrap_or("test").to_string(),
        corpus_size: v["corpus_size"].as_u64().unwrap_or(100),
        generated_at: v["generated_at"]
            .as_str()
            .unwrap_or("2026-01-01T00:00:00Z")
            .to_string(),
        middens_version: v["middens_version"].as_str().unwrap_or("0.1.0").to_string(),
        parameters: params,
    }
}

/// Get metadata from world.error, falling back to default.
fn get_metadata(world: &MiddensWorld) -> OutputMetadata {
    match &world.error {
        Some(s) if !s.is_empty() => deserialize_metadata(s),
        _ => default_metadata(),
    }
}

/// Store metadata into world.error.
fn store_metadata(world: &mut MiddensWorld, meta: &OutputMetadata) {
    world.error = Some(serialize_metadata(meta));
}

/// Process escape sequences in Cucumber string parameters.
/// Handles `\uXXXX` unicode escapes and `\"` escaped quotes.
fn unescape_string(s: &str) -> String {
    let mut result = String::new();
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' {
            match chars.peek() {
                Some(&'u') => {
                    chars.next(); // consume 'u'
                    let hex: String = chars.by_ref().take(4).collect();
                    if hex.len() == 4 {
                        if let Ok(code_point) = u32::from_str_radix(&hex, 16) {
                            if let Some(unicode_char) = char::from_u32(code_point) {
                                result.push(unicode_char);
                                continue;
                            }
                        }
                    }
                    // If parsing failed, put back the original
                    result.push('\\');
                    result.push('u');
                    result.push_str(&hex);
                }
                Some(&'"') => {
                    chars.next(); // consume '"'
                    result.push('"');
                }
                Some(&'\\') => {
                    chars.next(); // consume '\\'
                    result.push('\\');
                }
                _ => {
                    result.push('\\');
                }
            }
        } else {
            result.push(c);
        }
    }
    result
}

/// Parse YAML frontmatter from markdown text (between --- delimiters).
fn extract_frontmatter(markdown: &str) -> Option<String> {
    let trimmed = markdown.trim_start();
    if !trimmed.starts_with("---") {
        return None;
    }
    let after_first = &trimmed[3..];
    if let Some(end) = after_first.find("---") {
        Some(after_first[..end].to_string())
    } else {
        None
    }
}

/// Extract the body (everything after the closing --- of frontmatter).
fn extract_body(markdown: &str) -> String {
    let trimmed = markdown.trim_start();
    if !trimmed.starts_with("---") {
        return trimmed.to_string();
    }
    let after_first = &trimmed[3..];
    if let Some(end) = after_first.find("---") {
        after_first[end + 3..].to_string()
    } else {
        trimmed.to_string()
    }
}

// ===========================================================================
// Given steps — TechniqueResult construction
// ===========================================================================

#[given(expr = "a technique result named {string} with a summary {string}")]
fn given_technique_result(world: &mut MiddensWorld, name: String, summary: String) {
    world.technique_result = Some(TechniqueResult {
        name,
        summary,
        findings: vec![],
        tables: vec![],
        figures: vec![],
    });
}

#[given(expr = "an empty technique result named {string}")]
fn given_empty_technique_result(world: &mut MiddensWorld, name: String) {
    world.technique_result = Some(empty_result(&name));
}

// --- Findings ---

#[given(expr = "a finding {string} with integer value {int} described as {string}")]
fn given_finding_int(world: &mut MiddensWorld, label: String, value: i64, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!(value),
        description: Some(desc),
    });
}

#[given(expr = "a finding {string} with float value {float} described as {string}")]
fn given_finding_float(world: &mut MiddensWorld, label: String, value: f64, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    // For integer-like floats (e.g. 0.0), add a tiny epsilon so that
    // format_value's as_i64() returns None and the float formatting path
    // (4 decimal places) is used instead of the integer path.
    let json_value = if value.fract() == 0.0 && value.is_finite() {
        let nudged = value + f64::EPSILON * value.abs().max(1.0);
        serde_json::Number::from_f64(nudged)
            .map(serde_json::Value::Number)
            .unwrap_or_else(|| json!(value))
    } else {
        json!(value)
    };
    result.findings.push(Finding {
        label,
        value: json_value,
        description: Some(desc),
    });
}

#[given(expr = "a finding {string} with boolean value true described as {string}")]
fn given_finding_bool_true(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!(true),
        description: Some(desc),
    });
}

#[given(expr = "a finding {string} with boolean value false described as {string}")]
fn given_finding_bool_false(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!(false),
        description: Some(desc),
    });
}

#[given(expr = "a finding {string} with null value described as {string}")]
fn given_finding_null(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: serde_json::Value::Null,
        description: Some(desc),
    });
}

#[given(expr = "a finding {string} with string value {string} described as {string}")]
fn given_finding_string(world: &mut MiddensWorld, label: String, value: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!(value),
        description: Some(desc),
    });
}

#[given(regex = r#"^a finding "([^"]*)" with array value \[1,2,3\] described as "([^"]*)"$"#)]
fn given_finding_array(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!([1, 2, 3]),
        description: Some(desc),
    });
}

#[given(regex = r#"^a finding "([^"]*)" with object value \{"a":1\} described as "([^"]*)"$"#)]
fn given_finding_object_a1(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!({"a": 1}),
        description: Some(desc),
    });
}

#[given(
    regex = r#"^a finding "([^"]*)" with object value \{"key":"val"\} described as "([^"]*)"$"#
)]
fn given_finding_object_kv(world: &mut MiddensWorld, label: String, desc: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!({"key": "val"}),
        description: Some(desc),
    });
}

// --- Findings (no description) ---

#[given(expr = "a finding {string} with integer value {int} and no description")]
fn given_finding_int_no_desc(world: &mut MiddensWorld, label: String, value: i64) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.findings.push(Finding {
        label,
        value: json!(value),
        description: None,
    });
}

// --- DataTables ---

#[given(expr = "a data table {string} with columns {string} and {int} rows")]
fn given_data_table(world: &mut MiddensWorld, name: String, cols: String, num_rows: i64) {
    let columns: Vec<&str> = cols.split(',').collect();
    let table = make_data_table(&name, &columns, num_rows as usize);
    let result = world.technique_result.as_mut().expect("result must exist");
    result.tables.push(table);
}

// --- FigureSpecs ---

#[given(expr = "a figure spec titled {string} with a vega-lite bar chart spec")]
fn given_figure_spec(world: &mut MiddensWorld, title: String) {
    let result = world.technique_result.as_mut().expect("result must exist");
    result.figures.push(FigureSpec {
        title,
        kind: FigureKind::VegaLite {
            spec: json!({
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "mark": "bar",
                "encoding": {
                    "x": {"field": "tool", "type": "nominal"},
                    "y": {"field": "count", "type": "quantitative"}
                }
            }),
        },
    });
}

// --- OutputMetadata ---

#[given(expr = "output metadata with technique {string}, corpus size {int}, and version {string}")]
fn given_output_metadata(
    world: &mut MiddensWorld,
    technique: String,
    corpus_size: i64,
    version: String,
) {
    let meta = OutputMetadata {
        technique_name: technique,
        corpus_size: corpus_size as u64,
        generated_at: "2026-01-01T00:00:00Z".to_string(),
        middens_version: version,
        parameters: BTreeMap::new(),
    };
    store_metadata(world, &meta);
}

#[given(expr = "output metadata with parameters {string}")]
fn given_output_metadata_params(world: &mut MiddensWorld, params: String) {
    let mut meta = get_metadata(world);
    for pair in params.split(',') {
        let kv: Vec<&str> = pair.splitn(2, '=').collect();
        if kv.len() == 2 {
            meta.parameters.insert(kv[0].to_string(), kv[1].to_string());
        }
    }
    store_metadata(world, &meta);
}

#[given("output metadata with no parameters")]
fn given_output_metadata_no_params(world: &mut MiddensWorld) {
    let mut meta = get_metadata(world);
    meta.parameters.clear();
    store_metadata(world, &meta);
}

#[given("default output metadata")]
fn given_default_metadata(world: &mut MiddensWorld) {
    store_metadata(world, &default_metadata());
}

// --- Sparkline ---
// Sparkline values are stored as JSON array in world.cli_stderr.
// (cli_stderr is available since sparkline scenarios don't use JSON output.)

#[given(regex = r"^sparkline values \[((?:[^\]])+)\]$")]
fn given_sparkline_values_populated(world: &mut MiddensWorld, values_str: String) {
    let values: Vec<f64> = values_str
        .split(',')
        .map(|s| {
            s.trim()
                .parse::<f64>()
                .expect("invalid float in sparkline values")
        })
        .collect();
    world.cli_stderr = serde_json::to_string(&values).unwrap();
}

#[given(regex = r"^sparkline values \[\]$")]
fn given_sparkline_values_empty(world: &mut MiddensWorld) {
    world.cli_stderr = serde_json::to_string(&Vec::<f64>::new()).unwrap();
}

#[given(expr = "sparkline values from {float} to {float} in {int} steps")]
fn given_sparkline_values_range(world: &mut MiddensWorld, start: f64, end: f64, steps: i64) {
    let count = steps as usize;
    let values: Vec<f64> = (0..count)
        .map(|i| start + (end - start) * (i as f64) / ((count - 1).max(1) as f64))
        .collect();
    world.cli_stderr = serde_json::to_string(&values).unwrap();
}

// --- Bar chart ---
// Bar params are stored as JSON in world.cli_stderr.

#[given(expr = "a bar chart with label {string} value {float} max {float} width {int}")]
fn given_bar_chart(world: &mut MiddensWorld, label: String, value: f64, max: f64, width: i64) {
    world.cli_stderr = json!({
        "label": label,
        "value": value,
        "max": max,
        "width": width,
    })
    .to_string();
}

// --- ASCII table ---
// ASCII table input is stored in world.technique_result.tables (reusing that field
// since ASCII table scenarios don't otherwise use technique_result).

#[given(expr = "an ASCII data table {string} with columns {string} and {int} rows")]
fn given_ascii_table(world: &mut MiddensWorld, name: String, cols: String, num_rows: i64) {
    let columns: Vec<&str> = cols.split(',').collect();
    let table = make_data_table(&name, &columns, num_rows as usize);
    // Store in technique_result for retrieval in the When step
    if world.technique_result.is_none() {
        world.technique_result = Some(empty_result("__ascii_table__"));
    }
    world.technique_result.as_mut().unwrap().tables = vec![table];
}

#[given(
    expr = "an ASCII data table {string} with columns {string} and a row with a {int}-character value"
)]
fn given_ascii_table_long_value(
    world: &mut MiddensWorld,
    name: String,
    cols: String,
    char_count: i64,
) {
    let columns: Vec<String> = cols.split(',').map(|c| c.to_string()).collect();
    let long_value = "X".repeat(char_count as usize);
    let table = DataTable {
        name,
        columns,
        rows: vec![vec![json!(long_value)]],
        column_types: None,
    };
    if world.technique_result.is_none() {
        world.technique_result = Some(empty_result("__ascii_table__"));
    }
    world.technique_result.as_mut().unwrap().tables = vec![table];
}

// --- Integration: markov sessions ---

#[given("sessions with tool sequences for markov analysis")]
fn given_markov_sessions(world: &mut MiddensWorld) {
    let tools = &["Read", "Edit", "Read", "Bash", "Read", "Edit", "Bash"];
    let messages: Vec<Message> = tools
        .iter()
        .map(|name| Message {
            role: MessageRole::Assistant,
            timestamp: None,
            text: String::new(),
            thinking: None,
            reasoning_summary: None,
            reasoning_observability: middens::session::ReasoningObservability::Absent,
            tool_calls: vec![ToolCall {
                id: format!("call_{}", name),
                name: name.to_string(),
                input: serde_json::Value::Null,
            }],
            tool_results: vec![],
            classification: MessageClassification::Other,
            raw_content: vec![],
        })
        .collect();

    let session = Session {
        id: "markov_integration_test".to_string(),
        source_path: PathBuf::from("/tmp/test.jsonl"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages,
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Unknown,
        reasoning_observability: middens::session::SessionReasoningObservability::Unknown,
    };

    world.sessions = vec![session];
}

// ===========================================================================
// When steps — rendering
// ===========================================================================

#[when("I render markdown")]
fn when_render_markdown(world: &mut MiddensWorld) {
    let result = get_technique_result(world);
    let meta = get_metadata(world);
    let md = render_markdown(&result, &meta);
    world.cli_output = md;
}

#[when("I render JSON")]
fn when_render_json(world: &mut MiddensWorld) {
    let result = get_technique_result(world);
    let meta = get_metadata(world);
    let json_val = render_json(&result, &meta);
    // Store serialized JSON in cli_stderr so it doesn't clobber cli_output (markdown)
    world.cli_stderr = serde_json::to_string(&json_val).unwrap();
}

#[when(expr = "I render a sparkline with width {int}")]
fn when_render_sparkline(world: &mut MiddensWorld, width: i64) {
    let values: Vec<f64> =
        serde_json::from_str(&world.cli_stderr).expect("sparkline values not set in cli_stderr");
    let result = render_ascii_sparkline(&values, width as usize);
    world.cli_output = result;
}

#[when("I render the bar chart")]
fn when_render_bar(world: &mut MiddensWorld) {
    let params: serde_json::Value =
        serde_json::from_str(&world.cli_stderr).expect("bar params not set in cli_stderr");
    let label = params["label"].as_str().unwrap();
    let value = params["value"].as_f64().unwrap();
    let max = params["max"].as_f64().unwrap();
    let width = params["width"].as_u64().unwrap() as usize;
    let result = render_ascii_bar(label, value, max, width);
    world.cli_output = result;
}

#[when(expr = "I render the ASCII table with max column width {int}")]
fn when_render_ascii_table(world: &mut MiddensWorld, max_width: i64) {
    let table = world
        .technique_result
        .as_ref()
        .expect("technique_result must be set")
        .tables
        .first()
        .expect("no table in technique_result")
        .clone();
    let result = render_ascii_table(&table, max_width as usize);
    world.cli_output = result;
}

#[when("I render the technique result as markdown with default metadata")]
fn when_render_technique_result_markdown(world: &mut MiddensWorld) {
    let result = get_technique_result(world);
    let meta = default_metadata();
    let md = render_markdown(&result, &meta);
    world.cli_output = md;
}

#[when("I render the technique result as JSON with default metadata")]
fn when_render_technique_result_json(world: &mut MiddensWorld) {
    let result = get_technique_result(world);
    let meta = default_metadata();
    let json_val = render_json(&result, &meta);
    world.cli_stderr = serde_json::to_string(&json_val).unwrap();
}

// ===========================================================================
// Then steps — Markdown assertions
// ===========================================================================

#[then("the markdown should contain YAML frontmatter")]
fn then_markdown_has_frontmatter(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    assert!(
        extract_frontmatter(md).is_some(),
        "Expected YAML frontmatter (between --- delimiters) but found none.\nMarkdown:\n{}",
        md
    );
}

#[then(expr = "the frontmatter should have key {string} with value {string}")]
fn then_frontmatter_key_value(world: &mut MiddensWorld, key: String, value: String) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    let expected_pattern = format!("{}: ", key);
    let line = fm
        .lines()
        .find(|l| l.trim_start().starts_with(&expected_pattern))
        .unwrap_or_else(|| panic!("frontmatter key '{}' not found in:\n{}", key, fm));
    let actual = line
        .trim_start()
        .strip_prefix(&expected_pattern)
        .unwrap()
        .trim();
    let actual_unquoted = actual.trim_matches('"').trim_matches('\'');
    assert_eq!(
        actual_unquoted, value,
        "frontmatter key '{}' expected '{}', got '{}'",
        key, value, actual_unquoted
    );
}

#[then(expr = "the frontmatter should have key {string}")]
fn then_frontmatter_has_key(world: &mut MiddensWorld, key: String) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    assert!(
        fm.contains(&format!("{}:", key)) || fm.contains(&format!("{} :", key)),
        "frontmatter key '{}' not found in:\n{}",
        key,
        fm
    );
}

#[then(expr = "the frontmatter should contain a {string} map")]
fn then_frontmatter_contains_map(world: &mut MiddensWorld, key: String) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    assert!(
        fm.contains(&format!("{}:", key)),
        "frontmatter should contain a '{}' map, but frontmatter is:\n{}",
        key,
        fm
    );
}

#[then(expr = "the frontmatter parameter {string} should be {string}")]
fn then_frontmatter_param(world: &mut MiddensWorld, param: String, expected: String) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    let search = format!("{}: ", param);
    let line = fm
        .lines()
        .find(|l| l.contains(&search))
        .unwrap_or_else(|| panic!("parameter '{}' not found in frontmatter:\n{}", param, fm));
    let actual = line
        .split(':')
        .nth(1)
        .expect("malformed param line")
        .trim()
        .trim_matches('"')
        .trim_matches('\'');
    assert_eq!(
        actual, expected,
        "parameter '{}' expected '{}', got '{}'",
        param, expected, actual
    );
}

#[then(expr = "the frontmatter should not contain {string}")]
fn then_frontmatter_not_contain(world: &mut MiddensWorld, text: String) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    assert!(
        !fm.contains(&text),
        "frontmatter should NOT contain '{}', but it does:\n{}",
        text,
        fm
    );
}

#[then(expr = "the markdown body should start with {string}")]
fn then_body_starts_with(world: &mut MiddensWorld, expected: String) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let body_trimmed = body.trim_start();
    assert!(
        body_trimmed.starts_with(&expected),
        "Expected body to start with '{}', but body starts with: '{}'",
        expected,
        &body_trimmed[..body_trimmed.len().min(80)]
    );
}

#[then(expr = "the markdown body should contain {string}")]
fn then_body_contains(world: &mut MiddensWorld, expected: String) {
    let md = &world.cli_output;
    let body = extract_body(md);
    assert!(
        body.contains(&expected),
        "Expected body to contain '{}', but it doesn't.\nBody:\n{}",
        expected,
        body
    );
}

#[then("the summary should appear after the title")]
fn then_summary_after_title(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let title_pos = body.find("# ").expect("title not found");
    let newline_after_title = body[title_pos..]
        .find('\n')
        .expect("no newline after title");
    let after_title = &body[title_pos + newline_after_title..];
    let trimmed = after_title.trim_start();
    assert!(
        !trimmed.is_empty(),
        "Expected content after title, but body after title is empty"
    );
}

#[then("the markdown body after the title should not contain a summary paragraph")]
fn then_no_summary(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let title_pos = body.find("# ").expect("title not found");
    let newline_after_title = body[title_pos..]
        .find('\n')
        .expect("no newline after title");
    let after_title = &body[title_pos + newline_after_title..];
    let trimmed = after_title.trim();
    assert!(
        trimmed.is_empty()
            || trimmed.starts_with('#')
            || trimmed.starts_with('|')
            || trimmed.starts_with("---"),
        "Expected no summary paragraph after title, but found: '{}'",
        &trimmed[..trimmed.len().min(120)]
    );
}

#[then(expr = "the markdown should contain a pipe table with columns {string}, {string}, {string}")]
fn then_pipe_table_with_columns(
    world: &mut MiddensWorld,
    col1: String,
    col2: String,
    col3: String,
) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let has_header = body.lines().any(|line| {
        line.contains('|') && line.contains(&col1) && line.contains(&col2) && line.contains(&col3)
    });
    assert!(
        has_header,
        "Expected pipe table with columns '{}', '{}', '{}' but none found.\nBody:\n{}",
        col1, col2, col3, body
    );
}

#[then(expr = "the findings table should have {int} data rows")]
fn then_findings_table_rows(world: &mut MiddensWorld, expected: i64) {
    let md = &world.cli_output;
    let body = extract_body(md);
    // Find the Findings section specifically
    let findings_start = body.find("## Findings");
    let section = if let Some(start) = findings_start {
        let section_text = &body[start..];
        let end = section_text[3..]
            .find("\n## ")
            .map(|p| p + 3)
            .unwrap_or(section_text.len());
        &section_text[..end]
    } else {
        // If no ## Findings heading, look for pipe table in the body
        &body
    };
    let pipe_lines: Vec<&str> = section
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .collect();
    let data_rows = if pipe_lines.len() > 2 {
        pipe_lines.len() - 2
    } else {
        0
    };
    assert_eq!(
        data_rows, expected as usize,
        "Expected {} data rows in findings table, got {}",
        expected, data_rows
    );
}

#[then("the markdown should not contain a findings pipe table")]
fn then_no_findings_table(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let has_findings_table = body
        .lines()
        .any(|l| l.contains("Finding") && l.contains('|'));
    assert!(
        !has_findings_table,
        "Expected no findings pipe table but one was found.\nBody:\n{}",
        body
    );
}

#[then(expr = r#"the findings table should contain the value {string} for finding {string}"#)]
fn then_finding_value(world: &mut MiddensWorld, expected_value: String, finding_label: String) {
    let md = &world.cli_output;
    let body = extract_body(md);
    // Handle unicode escapes like \u2014 that Cucumber passes as literal strings
    let expected = unescape_string(&expected_value);
    let row = body
        .lines()
        .find(|l| l.contains('|') && l.contains(&finding_label))
        .unwrap_or_else(|| {
            panic!(
                "Finding '{}' not found in pipe table.\nBody:\n{}",
                finding_label, body
            )
        });
    assert!(
        row.contains(&expected),
        "Finding '{}' row does not contain value '{}'. Row: {}",
        finding_label,
        expected,
        row
    );
}

#[then(expr = r#"the findings table row for {string} should contain {string}"#)]
fn then_finding_row_contains(world: &mut MiddensWorld, finding_label: String, expected: String) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let row = body
        .lines()
        .find(|l| l.contains('|') && l.contains(&finding_label))
        .unwrap_or_else(|| {
            panic!(
                "Finding '{}' not found in pipe table.\nBody:\n{}",
                finding_label, body
            )
        });
    assert!(
        row.contains(&expected),
        "Finding '{}' row does not contain '{}'. Row: {}",
        finding_label,
        expected,
        row
    );
}

#[then(expr = "the markdown should contain {string}")]
fn then_markdown_contains(world: &mut MiddensWorld, expected: String) {
    let md = &world.cli_output;
    assert!(
        md.contains(&expected),
        "Expected markdown to contain '{}' but it doesn't.\nMarkdown:\n{}",
        expected,
        md
    );
}

#[then(expr = "the section {string} should contain a pipe table")]
fn then_section_has_pipe_table(world: &mut MiddensWorld, section_name: String) {
    let md = &world.cli_output;
    let header = format!("## {}", section_name);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found in markdown", section_name));
    let after_header = &md[header_pos..];
    let has_pipe = after_header.lines().skip(1).any(|l| l.contains('|'));
    assert!(
        has_pipe,
        "Section '{}' does not contain a pipe table",
        section_name
    );
}

#[then(expr = r#"the {string} section should show the first {int} rows"#)]
fn then_section_first_rows(world: &mut MiddensWorld, section: String, count: i64) {
    let md = &world.cli_output;
    let header = format!("## {}", section);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found", section));
    let section_text = &md[header_pos..];
    let end = section_text[3..]
        .find("\n## ")
        .map(|p| p + 3)
        .unwrap_or(section_text.len());
    let section_text = &section_text[..end];
    let pipe_lines: Vec<&str> = section_text
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .collect();
    assert!(
        pipe_lines.len() >= 2 + count as usize,
        "Expected at least {} data rows in first batch, but total pipe lines = {}",
        count,
        pipe_lines.len()
    );
    let first_data = pipe_lines.get(2).expect("missing first data row");
    assert!(
        first_data.contains("r0c0") || first_data.contains("r0"),
        "First data row doesn't look like row 0: {}",
        first_data
    );
}

#[then(expr = r#"the {string} section should contain an ellipsis row {string}"#)]
fn then_section_has_ellipsis(world: &mut MiddensWorld, section: String, ellipsis: String) {
    let md = &world.cli_output;
    let header = format!("## {}", section);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found", section));
    let section_text = &md[header_pos..];
    assert!(
        section_text.contains(&ellipsis),
        "Section '{}' should contain ellipsis '{}' but doesn't.\nSection:\n{}",
        section,
        ellipsis,
        section_text
    );
}

#[then(expr = r#"the {string} section should show the last {int} rows"#)]
fn then_section_last_rows(world: &mut MiddensWorld, section: String, count: i64) {
    let md = &world.cli_output;
    let header = format!("## {}", section);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found", section));
    let section_text = &md[header_pos..];
    let end = section_text[3..]
        .find("\n## ")
        .map(|p| p + 3)
        .unwrap_or(section_text.len());
    let section_text = &section_text[..end];
    let pipe_lines: Vec<&str> = section_text
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .collect();
    let data_lines: Vec<&str> = pipe_lines.iter().skip(2).cloned().collect();
    let tail: Vec<&str> = data_lines
        .iter()
        .rev()
        .take(count as usize)
        .rev()
        .cloned()
        .collect();
    assert_eq!(
        tail.len(),
        count as usize,
        "Expected {} tail rows, got {}",
        count,
        tail.len()
    );
}

#[then(expr = r#"the {string} section should show all {int} data rows"#)]
fn then_section_all_rows(world: &mut MiddensWorld, section: String, expected: i64) {
    let md = &world.cli_output;
    let header = format!("## {}", section);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found", section));
    let section_text = &md[header_pos..];
    let end = section_text[3..]
        .find("\n## ")
        .map(|p| p + 3)
        .unwrap_or(section_text.len());
    let section_text = &section_text[..end];
    let pipe_lines: Vec<&str> = section_text
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .collect();
    let data_rows = pipe_lines.len().saturating_sub(2);
    assert_eq!(
        data_rows, expected as usize,
        "Expected {} data rows but got {}",
        expected, data_rows
    );
}

#[then(expr = r#"the {string} section should not contain an ellipsis row"#)]
fn then_section_no_ellipsis(world: &mut MiddensWorld, section: String) {
    let md = &world.cli_output;
    let header = format!("## {}", section);
    let header_pos = md
        .find(&header)
        .unwrap_or_else(|| panic!("Section '{}' not found", section));
    let section_text = &md[header_pos..];
    assert!(
        !section_text.contains("..."),
        "Section '{}' should NOT contain ellipsis but does",
        section
    );
}

#[then("the markdown should contain a JSON code block with the figure spec")]
fn then_markdown_json_code_block(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    assert!(
        md.contains("```json") || md.contains("```JSON"),
        "Expected a JSON code block but none found.\nMarkdown:\n{}",
        md
    );
    let start = md
        .find("```json")
        .or_else(|| md.find("```JSON"))
        .expect("no json code block");
    let after_fence = &md[start + 7..];
    let end = after_fence.find("```").expect("unclosed code block");
    let json_str = &after_fence[..end].trim();
    let parsed: Result<serde_json::Value, _> = serde_json::from_str(json_str);
    assert!(
        parsed.is_ok(),
        "JSON in code block is not valid JSON: {}",
        json_str
    );
}

#[then("the markdown should have no data table sections")]
fn then_no_data_table_sections(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let body = extract_body(md);
    let h2_count = body.lines().filter(|l| l.starts_with("## ")).count();
    assert_eq!(
        h2_count, 0,
        "Expected no ## sections but found {}",
        h2_count
    );
}

#[then("the markdown should have no figure sections")]
fn then_no_figure_sections(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    assert!(
        !md.contains("```json"),
        "Expected no figure JSON code blocks but found one"
    );
}

// ===========================================================================
// Then steps — JSON assertions
// ===========================================================================

/// Helper: get JSON value from world.cli_stderr (where render_json stores it).
fn get_json_result(world: &MiddensWorld) -> serde_json::Value {
    serde_json::from_str(&world.cli_stderr).expect("JSON result not set or invalid in cli_stderr")
}

#[then("the JSON output should be a valid JSON object")]
fn then_json_valid(world: &mut MiddensWorld) {
    let json_val = get_json_result(world);
    assert!(
        json_val.is_object(),
        "Expected JSON object, got: {:?}",
        json_val
    );
}

#[then(expr = "the JSON should have a {string} object")]
fn then_json_has_object(world: &mut MiddensWorld, key: String) {
    let json_val = get_json_result(world);
    let obj = json_val.as_object().expect("not an object");
    assert!(
        obj.get(&key).map_or(false, |v| v.is_object()),
        "Expected '{}' to be an object in JSON output. Keys: {:?}",
        key,
        obj.keys().collect::<Vec<_>>()
    );
}

#[then(expr = "the JSON should have a {string} array")]
fn then_json_has_array(world: &mut MiddensWorld, key: String) {
    let json_val = get_json_result(world);
    let obj = json_val.as_object().expect("not an object");
    assert!(
        obj.get(&key).map_or(false, |v| v.is_array()),
        "Expected '{}' to be an array in JSON output. Keys: {:?}",
        key,
        obj.keys().collect::<Vec<_>>()
    );
}

#[then(expr = "the JSON metadata {string} should be {string}")]
fn then_json_metadata_str(world: &mut MiddensWorld, key: String, expected: String) {
    let json_val = get_json_result(world);
    let meta = json_val
        .get("metadata")
        .expect("no metadata")
        .as_object()
        .expect("metadata not object");
    let actual = meta
        .get(&key)
        .unwrap_or_else(|| panic!("metadata key '{}' not found", key));
    let actual_str = match actual {
        serde_json::Value::String(s) => s.clone(),
        other => other.to_string(),
    };
    assert_eq!(
        actual_str, expected,
        "metadata '{}' expected '{}', got '{}'",
        key, expected, actual_str
    );
}

#[then(expr = "the JSON metadata {string} should be {int}")]
fn then_json_metadata_int(world: &mut MiddensWorld, key: String, expected: i64) {
    let json_val = get_json_result(world);
    let meta = json_val
        .get("metadata")
        .expect("no metadata")
        .as_object()
        .expect("metadata not object");
    let actual = meta
        .get(&key)
        .unwrap_or_else(|| panic!("metadata key '{}' not found", key));
    // Try as i64 first, then as u64 converted to i64
    let actual_int = actual
        .as_i64()
        .or_else(|| actual.as_u64().map(|u| u as i64))
        .unwrap_or_else(|| panic!("metadata '{}' is not an integer: {:?}", key, actual));
    assert_eq!(
        actual_int, expected,
        "metadata '{}' expected {}, got {}",
        key, expected, actual_int
    );
}

#[then(expr = "the JSON metadata should have {string}")]
fn then_json_metadata_has_key(world: &mut MiddensWorld, key: String) {
    let json_val = get_json_result(world);
    let meta = json_val
        .get("metadata")
        .expect("no metadata")
        .as_object()
        .expect("metadata not object");
    assert!(
        meta.contains_key(&key),
        "metadata should have key '{}' but doesn't. Keys: {:?}",
        key,
        meta.keys().collect::<Vec<_>>()
    );
}

#[then(expr = "the JSON metadata {string} should have key {string} with value {string}")]
fn then_json_metadata_nested(
    world: &mut MiddensWorld,
    map_key: String,
    param_key: String,
    expected: String,
) {
    let json_val = get_json_result(world);
    let meta = json_val
        .get("metadata")
        .expect("no metadata")
        .as_object()
        .expect("metadata not object");
    let map = meta
        .get(&map_key)
        .unwrap_or_else(|| panic!("metadata '{}' not found", map_key))
        .as_object()
        .unwrap_or_else(|| panic!("metadata '{}' is not an object", map_key));
    let actual = map
        .get(&param_key)
        .unwrap_or_else(|| panic!("key '{}' not in metadata '{}'", param_key, map_key));
    let actual_str = match actual {
        serde_json::Value::String(s) => s.clone(),
        other => other.to_string(),
    };
    assert_eq!(actual_str, expected);
}

#[then(expr = "the JSON findings array should have {int} elements")]
fn then_json_findings_count(world: &mut MiddensWorld, expected: i64) {
    let json_val = get_json_result(world);
    let findings = json_val
        .get("findings")
        .expect("no findings")
        .as_array()
        .expect("findings not array");
    assert_eq!(
        findings.len(),
        expected as usize,
        "Expected {} findings, got {}",
        expected,
        findings.len()
    );
}

// Use regex to avoid ambiguity with the float step: require integer pattern only
#[then(regex = r#"^JSON finding "([^"]*)" should have value (\d+)$"#)]
fn then_json_finding_int(world: &mut MiddensWorld, label: String, expected: i64) {
    let json_val = get_json_result(world);
    let findings = json_val
        .get("findings")
        .expect("no findings")
        .as_array()
        .expect("findings not array");
    let finding = findings
        .iter()
        .find(|f| f.get("label").and_then(|l| l.as_str()) == Some(&label))
        .unwrap_or_else(|| panic!("finding '{}' not found in JSON", label));
    let actual = finding
        .get("value")
        .expect("finding has no value")
        .as_i64()
        .expect("value not integer");
    assert_eq!(actual, expected);
}

#[then(expr = "JSON finding {string} should have value true")]
fn then_json_finding_true(world: &mut MiddensWorld, label: String) {
    let json_val = get_json_result(world);
    let findings = json_val
        .get("findings")
        .expect("no findings")
        .as_array()
        .expect("findings not array");
    let finding = findings
        .iter()
        .find(|f| f.get("label").and_then(|l| l.as_str()) == Some(&label))
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    assert_eq!(finding.get("value").unwrap(), &json!(true));
}

#[then(regex = r#"^JSON finding "([^"]*)" should have value (\d+\.\d+)$"#)]
fn then_json_finding_float(world: &mut MiddensWorld, label: String, expected: f64) {
    let json_val = get_json_result(world);
    let findings = json_val
        .get("findings")
        .expect("no findings")
        .as_array()
        .expect("findings not array");
    let finding = findings
        .iter()
        .find(|f| f.get("label").and_then(|l| l.as_str()) == Some(&label))
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    let actual = finding
        .get("value")
        .expect("finding has no value")
        .as_f64()
        .expect("value not float");
    assert!(
        (actual - expected).abs() < 1e-9,
        "Expected {}, got {}",
        expected,
        actual
    );
}

#[then(expr = "JSON finding {string} should have null value")]
fn then_json_finding_null(world: &mut MiddensWorld, label: String) {
    let json_val = get_json_result(world);
    let findings = json_val
        .get("findings")
        .expect("no findings")
        .as_array()
        .expect("findings not array");
    let finding = findings
        .iter()
        .find(|f| f.get("label").and_then(|l| l.as_str()) == Some(&label))
        .unwrap_or_else(|| panic!("finding '{}' not found", label));
    assert!(
        finding.get("value").unwrap().is_null(),
        "Expected null value for '{}'",
        label
    );
}

#[then(expr = "the JSON tables array should have {int} element")]
fn then_json_tables_count_singular(world: &mut MiddensWorld, expected: i64) {
    then_json_tables_count_impl(world, expected);
}

fn then_json_tables_count_impl(world: &mut MiddensWorld, expected: i64) {
    let json_val = get_json_result(world);
    let tables = json_val
        .get("tables")
        .expect("no tables")
        .as_array()
        .expect("tables not array");
    assert_eq!(tables.len(), expected as usize);
}

#[then(expr = "JSON table {string} should have {int} columns")]
fn then_json_table_columns(world: &mut MiddensWorld, name: String, expected: i64) {
    let json_val = get_json_result(world);
    let tables = json_val
        .get("tables")
        .expect("no tables")
        .as_array()
        .expect("tables not array");
    let table = tables
        .iter()
        .find(|t| t.get("name").and_then(|n| n.as_str()) == Some(&name))
        .unwrap_or_else(|| panic!("table '{}' not found", name));
    let cols = table
        .get("columns")
        .expect("no columns")
        .as_array()
        .expect("columns not array");
    assert_eq!(cols.len(), expected as usize);
}

#[then(expr = "JSON table {string} should have {int} rows")]
fn then_json_table_rows(world: &mut MiddensWorld, name: String, expected: i64) {
    let json_val = get_json_result(world);
    let tables = json_val
        .get("tables")
        .expect("no tables")
        .as_array()
        .expect("tables not array");
    let table = tables
        .iter()
        .find(|t| t.get("name").and_then(|n| n.as_str()) == Some(&name))
        .unwrap_or_else(|| panic!("table '{}' not found", name));
    let rows = table
        .get("rows")
        .expect("no rows")
        .as_array()
        .expect("rows not array");
    assert_eq!(rows.len(), expected as usize);
}

#[then(expr = "the JSON figures array should have {int} element")]
fn then_json_figures_count_singular(world: &mut MiddensWorld, expected: i64) {
    then_json_figures_count_impl(world, expected);
}

fn then_json_figures_count_impl(world: &mut MiddensWorld, expected: i64) {
    let json_val = get_json_result(world);
    let figures = json_val
        .get("figures")
        .expect("no figures")
        .as_array()
        .expect("figures not array");
    assert_eq!(figures.len(), expected as usize);
}

#[then(expr = "JSON figure {string} should have a {string} object")]
fn then_json_figure_has_spec(world: &mut MiddensWorld, title: String, key: String) {
    let json_val = get_json_result(world);
    let figures = json_val
        .get("figures")
        .expect("no figures")
        .as_array()
        .expect("figures not array");
    let figure = figures
        .iter()
        .find(|f| f.get("title").and_then(|t| t.as_str()) == Some(&title))
        .unwrap_or_else(|| panic!("figure '{}' not found", title));
    // FigureSpec serializes as {title, kind: {type: "vegaLite", spec: {...}}}
    // Check both top-level and inside kind for backwards compat with feature files
    let found = figure.get(&key).map_or(false, |v| v.is_object())
        || figure
            .get("kind")
            .and_then(|k| k.get(&key))
            .map_or(false, |v| v.is_object());
    assert!(
        found,
        "figure '{}' should have '{}' object (checked top-level and kind)",
        title, key
    );
}

#[then(expr = "the JSON {string} array should be empty")]
fn then_json_array_empty(world: &mut MiddensWorld, key: String) {
    let json_val = get_json_result(world);
    let arr = json_val
        .get(&key)
        .unwrap_or_else(|| panic!("key '{}' not found", key))
        .as_array()
        .unwrap_or_else(|| panic!("'{}' is not an array", key));
    assert!(
        arr.is_empty(),
        "Expected '{}' to be empty, got {}",
        key,
        arr.len()
    );
}

#[then(expr = "the JSON should contain summary {string}")]
fn then_json_has_summary(world: &mut MiddensWorld, expected: String) {
    let json_val = get_json_result(world);
    let summary = json_val
        .get("summary")
        .unwrap_or_else(|| panic!("JSON output has no 'summary' field"))
        .as_str()
        .unwrap_or_else(|| panic!("'summary' is not a string"));
    assert_eq!(
        summary, expected,
        "Expected summary '{}', got '{}'",
        expected, summary
    );
}

#[then(expr = "the JSON tables array should have {int} elements")]
fn then_json_tables_count_plural(world: &mut MiddensWorld, expected: i64) {
    then_json_tables_count_impl(world, expected);
}

#[then("the JSON output should round-trip through serde_json deserialization")]
fn then_json_roundtrips(world: &mut MiddensWorld) {
    let json_val = get_json_result(world);
    let serialized = serde_json::to_string(&json_val).expect("failed to serialize JSON to string");
    let deserialized: serde_json::Value =
        serde_json::from_str(&serialized).expect("failed to deserialize JSON from string");
    assert_eq!(
        json_val, deserialized,
        "JSON did not round-trip: original != deserialized"
    );
}

// ===========================================================================
// Then steps — Sparkline assertions
// ===========================================================================

#[then("the sparkline should contain all 8 block characters")]
fn then_sparkline_all_blocks(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let blocks = [
        '\u{2581}', '\u{2582}', '\u{2583}', '\u{2584}', '\u{2585}', '\u{2586}', '\u{2587}',
        '\u{2588}',
    ];
    for block in &blocks {
        assert!(
            result.contains(*block),
            "Sparkline should contain block '{}' but doesn't. Result: {}",
            block,
            result
        );
    }
}

#[then(expr = "the sparkline should have {int} characters")]
fn then_sparkline_length(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let char_count = result.chars().count();
    assert_eq!(
        char_count, expected as usize,
        "Expected sparkline to have {} chars, got {}. Result: {}",
        expected, char_count, result
    );
}

#[then("the first sparkline character should be the lowest block")]
fn then_sparkline_first_lowest(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let first = result.chars().next().expect("sparkline is empty");
    assert_eq!(
        first, '\u{2581}',
        "Expected first char to be lowest block (U+2581), got '{}'",
        first
    );
}

#[then("the last sparkline character should be the highest block")]
fn then_sparkline_last_highest(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let last = result.chars().last().expect("sparkline is empty");
    assert_eq!(
        last, '\u{2588}',
        "Expected last char to be highest block (U+2588), got '{}'",
        last
    );
}

#[then("the sparkline should be empty")]
fn then_sparkline_empty(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        result.is_empty(),
        "Expected empty sparkline, got: '{}'",
        result
    );
}

#[then(expr = "the sparkline should have at most {int} characters")]
fn then_sparkline_at_most(world: &mut MiddensWorld, max_chars: i64) {
    let result = &world.cli_output;
    let char_count = result.chars().count();
    assert!(
        char_count <= max_chars as usize,
        "Expected sparkline to have at most {} chars, got {}. Result: {}",
        max_chars,
        char_count,
        result
    );
}

#[then("every sparkline character should be the same mid-level block")]
fn then_sparkline_all_mid(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(!result.is_empty(), "Sparkline is empty");
    let first = result.chars().next().unwrap();
    // The implementation uses SPARK_CHARS[3] = U+2584 for all-equal values
    assert_eq!(
        first, '\u{2584}',
        "Expected mid-level block (U+2584), got '{}'",
        first
    );
    for ch in result.chars() {
        assert_eq!(
            ch, first,
            "Expected all chars to be the same, but found '{}' and '{}'",
            first, ch
        );
    }
}

// ===========================================================================
// Then steps — Bar chart assertions
// ===========================================================================

#[then(expr = "the bar output should contain {string}")]
fn then_bar_contains(world: &mut MiddensWorld, expected: String) {
    let result = &world.cli_output;
    assert!(
        result.contains(&expected),
        "Bar output should contain '{}' but doesn't. Output: {}",
        expected,
        result
    );
}

#[then("the bar output should contain filled block characters")]
fn then_bar_has_filled(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        result.contains('\u{2588}'),
        "Bar output should contain filled block characters (U+2588). Output: {}",
        result
    );
}

#[then("the bar output should contain empty block characters")]
fn then_bar_has_empty(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        result.contains('\u{2591}'),
        "Bar output should contain empty block characters (U+2591). Output: {}",
        result
    );
}

#[then(expr = "the bar output should show value {int}")]
fn then_bar_shows_value(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    assert!(
        result.contains(&expected.to_string()),
        "Bar output should show value '{}'. Output: {}",
        expected,
        result
    );
}

#[then("the bar output should not contain filled block characters")]
fn then_bar_no_filled(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        !result.contains('\u{2588}'),
        "Bar output should NOT contain full block U+2588. Output: {}",
        result
    );
}

#[then("the bar should be completely filled")]
fn then_bar_fully_filled(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let filled_count = result.chars().filter(|c| *c == '\u{2588}').count();
    let empty_count = result
        .chars()
        .filter(|c| *c == '\u{2591}' || *c == '\u{2592}')
        .count();
    assert!(
        filled_count > 0,
        "Bar should have filled blocks. Output: {}",
        result
    );
    assert_eq!(
        empty_count, 0,
        "Bar should have no empty blocks when completely filled. Output: {}",
        result
    );
}

#[then(expr = "the bar portion should be approximately {int} characters wide")]
fn then_bar_width(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let block_count = result
        .chars()
        .filter(|c| *c == '\u{2588}' || *c == '\u{2591}')
        .count();
    let tolerance = 2;
    assert!(
        (block_count as i64 - expected).abs() <= tolerance,
        "Expected bar portion width ~{}, got {}. Output: {}",
        expected,
        block_count,
        result
    );
}

// ===========================================================================
// Then steps — ASCII table assertions
// ===========================================================================

#[then(expr = "the ASCII table output should have a header row with {string}, {string}, {string}")]
fn then_ascii_table_header_3(world: &mut MiddensWorld, col1: String, col2: String, col3: String) {
    let result = &world.cli_output;
    let first_line = result.lines().next().expect("ASCII table is empty");
    assert!(
        first_line.contains(&col1) && first_line.contains(&col2) && first_line.contains(&col3),
        "Header should contain '{}', '{}', '{}'. Got: {}",
        col1,
        col2,
        col3,
        first_line
    );
}

#[then(expr = "the ASCII table output should have a header row with {string}")]
fn then_ascii_table_header_1(world: &mut MiddensWorld, col1: String) {
    let result = &world.cli_output;
    let first_line = result.lines().next().expect("ASCII table is empty");
    assert!(
        first_line.contains(&col1),
        "Header should contain '{}'. Got: {}",
        col1,
        first_line
    );
}

#[then("the ASCII table output should have a separator row")]
fn then_ascii_table_separator(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    assert!(
        lines.len() >= 2,
        "Expected at least 2 lines (header + separator)"
    );
    let sep_line = lines[1];
    assert!(
        sep_line.contains('-'),
        "Second line should be a separator. Got: {}",
        sep_line
    );
}

#[then(expr = "the ASCII table output should have {int} data rows")]
fn then_ascii_table_data_rows(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    let data_count = lines.len().saturating_sub(2);
    assert_eq!(
        data_count, expected as usize,
        "Expected {} data rows, got {}. Output:\n{}",
        expected, data_count, result
    );
}

#[then(expr = "no cell in the ASCII table should exceed {int} characters")]
fn then_ascii_table_max_width(world: &mut MiddensWorld, max_width: i64) {
    let result = &world.cli_output;
    for line in result.lines() {
        // The ASCII table uses two-space column separators.
        // Split by "  " (double-space) to get cells.
        let cells: Vec<&str> = line.split("  ").collect();
        for cell in &cells {
            let trimmed = cell.trim();
            if !trimmed.is_empty()
                && !trimmed
                    .chars()
                    .all(|c| c == '-' || c == '=' || c == '\u{2500}')
            {
                assert!(
                    trimmed.chars().count() <= max_width as usize,
                    "Cell '{}' exceeds max width of {}",
                    trimmed,
                    max_width
                );
            }
        }
    }
}

#[then(expr = "the ASCII table should show the first {int} data rows")]
fn then_ascii_table_first_rows(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    let data_lines = &lines[2..];
    assert!(
        data_lines.len() >= expected as usize,
        "Expected at least {} data lines, got {}",
        expected,
        data_lines.len()
    );
    assert!(
        data_lines[0].contains("r0"),
        "First data row should reference r0. Got: {}",
        data_lines[0]
    );
}

#[then("the ASCII table should have a summary row")]
fn then_ascii_table_summary_row(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        result.contains("...")
            || result.to_lowercase().contains("rows")
            || result.contains("omitted"),
        "Expected a summary row (with '...' or row count). Output:\n{}",
        result
    );
}

#[then(expr = "the ASCII table should show the last {int} data rows")]
fn then_ascii_table_last_rows(world: &mut MiddensWorld, _expected: i64) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    let last_line = lines.last().expect("no lines");
    // The last line should contain data from the last row of the input table
    assert!(
        !last_line.trim().is_empty(),
        "Last line should not be empty. Got: {}",
        last_line
    );
}

#[then(expr = "the ASCII table should have {int} visible data-like rows total")]
fn then_ascii_table_visible_rows(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    let data_like = lines.len().saturating_sub(2);
    assert_eq!(
        data_like, expected as usize,
        "Expected {} visible data-like rows, got {}",
        expected, data_like
    );
}

#[then(expr = "the ASCII table should show all {int} data rows")]
fn then_ascii_table_all_rows(world: &mut MiddensWorld, expected: i64) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    let data_count = lines.len().saturating_sub(2);
    assert_eq!(
        data_count, expected as usize,
        "Expected {} data rows, got {}. Output:\n{}",
        expected, data_count, result
    );
}

#[then("the ASCII table should not have a summary row")]
fn then_ascii_table_no_summary(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    assert!(
        !result.contains("...") && !result.to_lowercase().contains("omitted"),
        "Should not have a summary/ellipsis row. Output:\n{}",
        result
    );
}

#[then("all ASCII table rows should have the same total width")]
fn then_ascii_table_aligned(world: &mut MiddensWorld) {
    let result = &world.cli_output;
    let lines: Vec<&str> = result.lines().collect();
    assert!(
        lines.len() >= 2,
        "Need at least header + separator for alignment check"
    );
    let widths: Vec<usize> = lines.iter().map(|l| l.chars().count()).collect();
    let first = widths[0];
    for (i, w) in widths.iter().enumerate() {
        assert_eq!(
            *w, first,
            "Row {} has width {} but header has width {}. Output:\n{}",
            i, w, first, result
        );
    }
}

// ===========================================================================
// Then steps — Integration assertions
// ===========================================================================

#[then("the markdown frontmatter should parse as valid YAML")]
fn then_frontmatter_valid_yaml(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let fm = extract_frontmatter(md).expect("no frontmatter found");
    assert!(
        fm.lines().any(|l| l.contains(':')),
        "Frontmatter doesn't look like valid YAML:\n{}",
        fm
    );
}

#[then("the markdown body should be well-formed markdown")]
fn then_body_well_formed(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    let body = extract_body(md);
    assert!(body.contains("# "), "Body should have a title");
    let backtick_count = body.matches("```").count();
    assert_eq!(
        backtick_count % 2,
        0,
        "Unclosed code block: found {} ``` markers",
        backtick_count
    );
}

#[then("the markdown output should contain YAML frontmatter")]
fn then_integration_md_frontmatter(world: &mut MiddensWorld) {
    let md = &world.cli_output;
    assert!(
        extract_frontmatter(md).is_some(),
        "Integration markdown should have YAML frontmatter"
    );
}

#[then(expr = "the markdown output should contain {string}")]
fn then_integration_md_contains(world: &mut MiddensWorld, expected: String) {
    let md = &world.cli_output;
    assert!(
        md.contains(&expected),
        "Integration markdown should contain '{}'. Output:\n{}",
        expected,
        &md[..md.len().min(500)]
    );
}

#[then(expr = "the JSON output should have a non-empty {string} array")]
fn then_integration_json_nonempty(world: &mut MiddensWorld, key: String) {
    let json_val = get_json_result(world);
    let arr = json_val
        .get(&key)
        .unwrap_or_else(|| panic!("key '{}' not found in integration JSON", key))
        .as_array()
        .unwrap_or_else(|| panic!("'{}' is not an array", key));
    assert!(!arr.is_empty(), "Expected non-empty '{}' array", key);
}
