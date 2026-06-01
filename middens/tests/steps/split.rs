use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};
use tempfile::TempDir;

use middens::techniques::all_techniques;

use super::world::MiddensWorld;

fn middens_bin() -> &'static str {
    env!("CARGO_BIN_EXE_middens")
}

fn fixtures_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

fn temp_root(world: &mut MiddensWorld) -> PathBuf {
    if world.temp_dir.is_none() {
        world.temp_dir = Some(TempDir::new().expect("failed to create temp dir"));
    }

    world
        .temp_dir
        .as_ref()
        .expect("temp dir should be initialized")
        .path()
        .to_path_buf()
}

fn input_dir(world: &MiddensWorld) -> PathBuf {
    world
        .file_path
        .clone()
        .expect("file_path must be set to an analyze input directory")
}

fn output_dir(world: &MiddensWorld) -> PathBuf {
    world
        .output_path
        .clone()
        .expect("output_path must be set before running analyze")
}

fn xdg_data_home(world: &mut MiddensWorld) -> PathBuf {
    let xdg = temp_root(world).join("xdg");
    fs::create_dir_all(&xdg).expect("failed to create XDG data home for split tests");
    xdg
}

fn essential_technique_names() -> BTreeSet<String> {
    all_techniques()
        .into_iter()
        .filter(|technique| technique.is_essential())
        .map(|technique| technique.name().to_string())
        .collect()
}

fn files_with_extension(dir: &Path, extension: &str) -> Vec<PathBuf> {
    let entries = fs::read_dir(dir)
        .unwrap_or_else(|error| panic!("failed to read directory {}: {}", dir.display(), error));

    let mut files: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some(extension))
        .collect();
    files.sort();
    files
}

fn basenames(paths: &[PathBuf]) -> BTreeSet<String> {
    paths
        .iter()
        .filter_map(|path| path.file_stem())
        .filter_map(|stem| stem.to_str())
        .map(ToOwned::to_owned)
        .collect()
}

fn assert_population_outputs(dir: &Path) {
    let expected = essential_technique_names();
    let markdown = files_with_extension(dir, "md");
    let json = files_with_extension(dir, "json");

    assert_eq!(
        basenames(&markdown),
        expected,
        "markdown outputs in {} did not match essential techniques",
        dir.display()
    );
    assert_eq!(
        basenames(&json),
        expected,
        "JSON outputs in {} did not match essential techniques",
        dir.display()
    );
}

fn run_analyze(world: &mut MiddensWorld, split: bool) {
    run_analyze_with_args(world, split, &[]);
}

fn run_analyze_with_args(world: &mut MiddensWorld, split: bool, extra_args: &[&str]) {
    let xdg_data_home = xdg_data_home(world);
    let mut command = Command::new(middens_bin());
    command.arg("analyze").arg(input_dir(world));

    if split {
        command.arg("--split");
    }

    command.args(extra_args);
    command.arg("--output").arg(output_dir(world));
    command.env("XDG_DATA_HOME", &xdg_data_home);

    let output = command
        .output()
        .expect("failed to execute middens analyze binary");

    world.cli_output = String::from_utf8_lossy(&output.stdout).to_string();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    world.cli_exit_code = output.status.code();
}

#[given("a temporary mixed interactive, subagent, and autonomous corpus")]
fn given_temporary_mixed_interactive_subagent_and_autonomous_corpus(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let corpus_dir = root.join("mixed-corpus");
    let interactive_dir = corpus_dir.join("interactive");
    let subagent_dir = corpus_dir.join("subagent");
    let autonomous_dir = corpus_dir.join("autonomous");

    for (name, dir) in [
        ("interactive", &interactive_dir),
        ("subagent", &subagent_dir),
        ("autonomous", &autonomous_dir),
    ] {
        fs::create_dir_all(dir).unwrap_or_else(|error| {
            panic!(
                "failed to create {} corpus directory {}: {}",
                name,
                dir.display(),
                error
            )
        });
    }

    let fixtures = fixtures_dir();
    let copies = [
        (
            fixtures.join("claude_code_sample.jsonl"),
            interactive_dir.join("claude_code_sample.jsonl"),
        ),
        (
            fixtures.join("codex_sample.jsonl"),
            interactive_dir.join("codex_sample.jsonl"),
        ),
        (
            fixtures.join("openclaw_sample.jsonl"),
            subagent_dir.join("openclaw_sample.jsonl"),
        ),
    ];

    for (source, destination) in copies {
        fs::copy(&source, &destination).unwrap_or_else(|error| {
            panic!(
                "failed to copy fixture {} to {}: {}",
                source.display(),
                destination.display(),
                error
            )
        });
    }

    let autonomous_fixture = r#"{"type":"user","sessionId":"autonomous-fixture","timestamp":"2026-03-19T14:30:02Z","message":{"role":"user","content":"<system-reminder>queued autonomous loop tick</system-reminder>"}}
{"type":"assistant","sessionId":"autonomous-fixture","timestamp":"2026-03-19T14:30:03Z","message":{"role":"assistant","content":"Acknowledged."}}
"#;
    fs::write(
        autonomous_dir.join("autonomous_sample.jsonl"),
        autonomous_fixture,
    )
    .expect("failed to write autonomous fixture");

    world.file_path = Some(corpus_dir);
}

#[when("I run middens analyze with split on the mixed corpus")]
fn when_run_middens_analyze_with_split_on_the_mixed_corpus(world: &mut MiddensWorld) {
    run_analyze(world, true);
}

#[when("I run middens analyze without split on the mixed corpus")]
fn when_run_middens_analyze_without_split_on_the_mixed_corpus(world: &mut MiddensWorld) {
    run_analyze(world, false);
}

#[when(expr = "I run middens analyze with split on the mixed corpus using the {string} technique")]
fn when_run_middens_analyze_with_split_on_the_mixed_corpus_using_technique(
    world: &mut MiddensWorld,
    technique: String,
) {
    run_analyze_with_args(
        world,
        true,
        &["--techniques", technique.as_str(), "--timeout", "1800", "--force"],
    );
}

#[then(
    "the analyze output should be partitioned into interactive, subagent, and autonomous subdirectories"
)]
fn then_analyze_output_partitioned(world: &mut MiddensWorld) {
    let output_dir = output_dir(world);
    let interactive = output_dir.join("interactive");
    let subagent = output_dir.join("subagent");
    let autonomous = output_dir.join("autonomous");

    assert!(
        interactive.is_dir(),
        "missing interactive subdirectory at {}",
        interactive.display()
    );
    assert!(
        subagent.is_dir(),
        "missing subagent subdirectory at {}",
        subagent.display()
    );
    assert!(
        autonomous.is_dir(),
        "missing autonomous subdirectory at {}",
        autonomous.display()
    );
}

#[then("the analyze output should be flat with no population subdirectories")]
fn then_analyze_output_flat(world: &mut MiddensWorld) {
    let output_dir = output_dir(world);
    let interactive = output_dir.join("interactive");
    let subagent = output_dir.join("subagent");
    let autonomous = output_dir.join("autonomous");

    assert!(
        !interactive.exists(),
        "interactive subdirectory should not exist at {}",
        interactive.display()
    );
    assert!(
        !subagent.exists(),
        "subagent subdirectory should not exist at {}",
        subagent.display()
    );
    assert!(
        !autonomous.exists(),
        "autonomous subdirectory should not exist at {}",
        autonomous.display()
    );
}

#[then("the flat analyze output should contain technique markdown and JSON files")]
fn then_flat_analyze_output_contains_technique_markdown_and_json_files(world: &mut MiddensWorld) {
    assert_population_outputs(&output_dir(world));
}

#[then(expr = "the {string} analyze subdirectory should contain technique markdown and JSON files")]
fn then_population_subdirectory_contains_outputs(world: &mut MiddensWorld, population: String) {
    let dir = output_dir(world).join(&population);
    assert!(
        dir.is_dir(),
        "expected analyze subdirectory {} to exist",
        dir.display()
    );
    assert_population_outputs(&dir);
}

#[then(
    expr = "the split summary should report {int} interactive session, {int} subagent session, and {int} autonomous session"
)]
#[then(
    expr = "the split summary should report {int} interactive session, {int} subagent sessions, and {int} autonomous session"
)]
#[then(
    expr = "the split summary should report {int} interactive session, {int} subagent session, and {int} autonomous sessions"
)]
#[then(
    expr = "the split summary should report {int} interactive session, {int} subagent sessions, and {int} autonomous sessions"
)]
#[then(
    expr = "the split summary should report {int} interactive sessions, {int} subagent session, and {int} autonomous session"
)]
#[then(
    expr = "the split summary should report {int} interactive sessions, {int} subagent sessions, and {int} autonomous session"
)]
#[then(
    expr = "the split summary should report {int} interactive sessions, {int} subagent session, and {int} autonomous sessions"
)]
#[then(
    expr = "the split summary should report {int} interactive sessions, {int} subagent sessions, and {int} autonomous sessions"
)]
fn then_split_summary_reports_population_counts(
    world: &mut MiddensWorld,
    interactive_count: i32,
    subagent_count: i32,
    autonomous_count: i32,
) {
    let interactive_line = format!("interactive sessions: {}", interactive_count);
    let subagent_line = format!("subagent sessions: {}", subagent_count);
    let autonomous_line = format!("autonomous sessions: {}", autonomous_count);

    assert!(
        world.cli_stderr.contains(&interactive_line),
        "stderr did not contain {:?}\nactual stderr:\n{}",
        interactive_line,
        world.cli_stderr
    );
    assert!(
        world.cli_stderr.contains(&subagent_line),
        "stderr did not contain {:?}\nactual stderr:\n{}",
        subagent_line,
        world.cli_stderr
    );
    assert!(
        world.cli_stderr.contains(&autonomous_line),
        "stderr did not contain {:?}\nactual stderr:\n{}",
        autonomous_line,
        world.cli_stderr
    );
}

#[then(
    expr = "the split hsmm summaries should report {int} interactive session, {int} subagent sessions, and {int} autonomous session"
)]
fn then_split_hsmm_summaries_report_per_stratum_sessions(
    world: &mut MiddensWorld,
    interactive_count: i32,
    subagent_count: i32,
    autonomous_count: i32,
) {
    for (stratum, expected) in [
        ("interactive", interactive_count),
        ("subagent", subagent_count),
        ("autonomous", autonomous_count),
    ] {
        let path = output_dir(world).join(stratum).join("hsmm.json");
        let raw = fs::read_to_string(&path)
            .unwrap_or_else(|error| panic!("failed to read {}: {}", path.display(), error));
        let value: serde_json::Value = serde_json::from_str(&raw)
            .unwrap_or_else(|error| panic!("failed to parse {}: {}", path.display(), error));
        let summary = value
            .get("summary")
            .and_then(|summary| summary.as_str())
            .unwrap_or_else(|| panic!("{} did not contain a string summary", path.display()));
        let expected_phrase = format!("only {} sessions provided", expected);
        assert!(
            summary.contains(&expected_phrase),
            "{} summary should mention {:?}, got {:?}",
            stratum,
            expected_phrase,
            summary
        );
    }
}
