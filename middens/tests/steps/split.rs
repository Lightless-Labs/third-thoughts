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
    let xdg_data_home = xdg_data_home(world);
    let mut command = Command::new(middens_bin());
    command.arg("analyze").arg(input_dir(world));

    if split {
        command.arg("--split");
    }

    command.arg("--output").arg(output_dir(world));
    command.env("XDG_DATA_HOME", &xdg_data_home);

    let output = command
        .output()
        .expect("failed to execute middens analyze binary");

    world.cli_output = String::from_utf8_lossy(&output.stdout).to_string();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    world.cli_exit_code = output.status.code();
}

#[given("a temporary mixed interactive and subagent corpus")]
fn given_temporary_mixed_interactive_and_subagent_corpus(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let corpus_dir = root.join("mixed-corpus");
    let interactive_dir = corpus_dir.join("interactive");
    let subagent_dir = corpus_dir.join("subagent");

    fs::create_dir_all(&interactive_dir).unwrap_or_else(|error| {
        panic!(
            "failed to create interactive corpus directory {}: {}",
            interactive_dir.display(),
            error
        )
    });
    fs::create_dir_all(&subagent_dir).unwrap_or_else(|error| {
        panic!(
            "failed to create subagent corpus directory {}: {}",
            subagent_dir.display(),
            error
        )
    });

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

#[then("the analyze output should be partitioned into interactive and subagent subdirectories")]
fn then_analyze_output_partitioned(world: &mut MiddensWorld) {
    let output_dir = output_dir(world);
    let interactive = output_dir.join("interactive");
    let subagent = output_dir.join("subagent");

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
}

#[then("the analyze output should be flat with no population subdirectories")]
fn then_analyze_output_flat(world: &mut MiddensWorld) {
    let output_dir = output_dir(world);
    let interactive = output_dir.join("interactive");
    let subagent = output_dir.join("subagent");

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
    expr = "the split summary should report {int} interactive sessions and {int} subagent session"
)]
#[then(
    expr = "the split summary should report {int} interactive sessions and {int} subagent sessions"
)]
fn then_split_summary_reports_population_counts(
    world: &mut MiddensWorld,
    interactive_count: i32,
    subagent_count: i32,
) {
    let interactive_line = format!("interactive sessions: {}", interactive_count);
    let subagent_line = format!("subagent sessions: {}", subagent_count);

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
}
