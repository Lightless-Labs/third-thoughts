use std::process::Command;

use cucumber::{then, when};
use tempfile::TempDir;

use super::world::MiddensWorld;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Path to the compiled `middens` binary (resolved at compile time).
fn middens_bin() -> &'static str {
    env!("CARGO_BIN_EXE_middens")
}

/// Absolute path to the test fixtures directory.
fn fixtures_dir() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

/// Run the middens binary with the given args, storing stdout/stderr/exit code
/// in the world.
fn run_middens(world: &mut MiddensWorld, args: &[&str]) {
    let output = Command::new(middens_bin())
        .args(args)
        .output()
        .expect("failed to execute middens binary");

    world.cli_output = String::from_utf8_lossy(&output.stdout).to_string();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    world.cli_exit_code = output.status.code();
}

// ---------------------------------------------------------------------------
// When steps — parse
// ---------------------------------------------------------------------------

#[when(expr = "I run middens parse on the {string} fixture")]
fn when_parse_fixture(world: &mut MiddensWorld, fixture_name: String) {
    let fixture_path = fixtures_dir().join(&fixture_name);
    let path_str = fixture_path.to_string_lossy().to_string();
    run_middens(world, &["parse", &path_str]);
}

#[when("I run middens parse on a temporary empty file")]
fn when_parse_empty_file(world: &mut MiddensWorld) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    let empty_file = tmp.path().join("empty.jsonl");
    std::fs::write(&empty_file, "").expect("failed to write empty file");
    let path_str = empty_file.to_string_lossy().to_string();
    run_middens(world, &["parse", &path_str]);
    // Keep the temp dir alive until the scenario ends.
    world.temp_dir = Some(tmp);
}

#[when(expr = "I run middens parse on the {string} fixture with format {string}")]
fn when_parse_fixture_with_format(world: &mut MiddensWorld, fixture_name: String, format: String) {
    let fixture_path = fixtures_dir().join(&fixture_name);
    let path_str = fixture_path.to_string_lossy().to_string();
    run_middens(world, &["parse", &path_str, "--format", &format]);
}

// ---------------------------------------------------------------------------
// When steps — freeze
// ---------------------------------------------------------------------------

#[when("I run middens freeze on the test fixtures directory")]
fn when_freeze_fixtures(world: &mut MiddensWorld) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    let manifest_path = tmp.path().join("manifest.json");
    let fixtures = fixtures_dir();
    let fixtures_str = fixtures.to_string_lossy().to_string();
    let manifest_str = manifest_path.to_string_lossy().to_string();
    run_middens(world, &["freeze", &fixtures_str, "-o", &manifest_str]);
    world.output_path = Some(manifest_path);
    world.temp_dir = Some(tmp);
}

#[when("I run middens freeze on a non-existent directory")]
fn when_freeze_nonexistent(world: &mut MiddensWorld) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    let manifest_path = tmp.path().join("manifest.json");
    let nonexistent = tmp.path().join("does-not-exist");
    let nonexistent_str = nonexistent.to_string_lossy().to_string();
    let manifest_str = manifest_path.to_string_lossy().to_string();
    run_middens(world, &["freeze", &nonexistent_str, "-o", &manifest_str]);
    world.temp_dir = Some(tmp);
}

// ---------------------------------------------------------------------------
// When steps — list-techniques
// ---------------------------------------------------------------------------

#[when("I run middens list-techniques")]
fn when_list_techniques(world: &mut MiddensWorld) {
    run_middens(world, &["list-techniques"]);
}

#[when("I run middens list-techniques with the essential flag")]
fn when_list_techniques_essential(world: &mut MiddensWorld) {
    run_middens(world, &["list-techniques", "--essential"]);
}

// ---------------------------------------------------------------------------
// Then steps — exit code
// ---------------------------------------------------------------------------

// exit code step moved to pipeline.rs as parameterized version

#[then("the exit code should not be 0")]
fn then_exit_code_nonzero(world: &mut MiddensWorld) {
    let code = world.cli_exit_code.expect("process had no exit code");
    assert_ne!(
        code, 0,
        "Expected non-zero exit code, got 0.\nstdout: {}\nstderr: {}",
        world.cli_output, world.cli_stderr
    );
}

// ---------------------------------------------------------------------------
// Then steps — stdout assertions
// ---------------------------------------------------------------------------

#[then("stdout should be valid JSON")]
fn then_stdout_valid_json(world: &mut MiddensWorld) {
    let parsed: Result<serde_json::Value, _> = serde_json::from_str(&world.cli_output);
    assert!(
        parsed.is_ok(),
        "stdout is not valid JSON.\nstdout: {}\nparse error: {}",
        &world.cli_output[..world.cli_output.len().min(500)],
        parsed.unwrap_err()
    );
}

#[then(expr = "the parsed output should contain {int} session(s)")]
fn then_parsed_session_count(world: &mut MiddensWorld, expected: usize) {
    let sessions: serde_json::Value =
        serde_json::from_str(&world.cli_output).expect("stdout is not valid JSON");
    let arr = sessions.as_array().expect("expected JSON array in stdout");
    assert_eq!(
        arr.len(),
        expected,
        "Expected {} session(s), got {}",
        expected,
        arr.len()
    );
}

#[then(expr = "stdout should contain {string}")]
fn then_stdout_contains(world: &mut MiddensWorld, substring: String) {
    assert!(
        world.cli_output.contains(&substring),
        "Expected stdout to contain {:?}, but it did not.\nstdout: {}",
        substring,
        &world.cli_output[..world.cli_output.len().min(500)]
    );
}

#[then(expr = "stdout should list {int} technique rows")]
fn then_stdout_technique_row_count(world: &mut MiddensWorld, expected: usize) {
    // The output has a header line, a separator line, then one line per technique.
    // We count non-empty lines after the separator (the line of dashes).
    let lines: Vec<&str> = world.cli_output.lines().collect();
    let separator_pos = lines
        .iter()
        .position(|l| l.starts_with("---"))
        .expect("Could not find separator line in list-techniques output");
    let data_lines: Vec<&&str> = lines[separator_pos + 1..]
        .iter()
        .filter(|l| !l.trim().is_empty())
        .collect();
    assert_eq!(
        data_lines.len(),
        expected,
        "Expected {} technique rows, got {}.\nstdout: {}",
        expected,
        data_lines.len(),
        world.cli_output
    );
}

// ---------------------------------------------------------------------------
// Then steps — stderr assertions
// ---------------------------------------------------------------------------

#[then(expr = "stderr should contain {string}")]
fn then_stderr_contains(world: &mut MiddensWorld, substring: String) {
    assert!(
        world.cli_stderr.contains(&substring),
        "Expected stderr to contain {:?}, but it did not.\nstderr: {}",
        substring,
        &world.cli_stderr[..world.cli_stderr.len().min(500)]
    );
}

// ---------------------------------------------------------------------------
// Then steps — freeze / manifest assertions
// ---------------------------------------------------------------------------

#[then("the manifest file should exist")]
fn then_manifest_exists(world: &mut MiddensWorld) {
    let path = world
        .output_path
        .as_ref()
        .expect("No output_path set — did the freeze When step run?");
    assert!(
        path.exists(),
        "Manifest file does not exist at {}",
        path.display()
    );
}

#[then(expr = "the manifest should contain {int} entries")]
fn then_manifest_entry_count(world: &mut MiddensWorld, expected: usize) {
    let path = world
        .output_path
        .as_ref()
        .expect("No output_path set — did the freeze When step run?");
    let content = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("Failed to read manifest at {}: {}", path.display(), e));
    let manifest: serde_json::Value =
        serde_json::from_str(&content).expect("Manifest is not valid JSON");
    let entries = manifest["entries"]
        .as_array()
        .expect("Manifest missing 'entries' array");
    assert_eq!(
        entries.len(),
        expected,
        "Expected {} manifest entries, got {}",
        expected,
        entries.len()
    );
}
