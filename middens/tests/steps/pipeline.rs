use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};
use tempfile::TempDir;

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

fn parse_techniques(csv: &str) -> Vec<String> {
    csv.split(',')
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn output_dir(world: &MiddensWorld) -> PathBuf {
    world
        .output_path
        .clone()
        .expect("output_path must be set before running analyze")
}

fn run_analyze(world: &mut MiddensWorld, input_dir: &Path, all: bool, techniques: Option<&str>) {
    let output_dir = output_dir(world);

    let mut command = Command::new(middens_bin());
    command.arg("analyze").arg(input_dir);

    if all {
        command.arg("--all");
    }

    if let Some(techniques) = techniques {
        command.arg("--techniques").arg(techniques);
    }

    command.arg("--output").arg(&output_dir);

    let output = command
        .output()
        .expect("failed to execute middens analyze binary");

    world.cli_output = String::from_utf8_lossy(&output.stdout).to_string();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    world.cli_exit_code = output.status.code();
}

#[then(expr = "the exit code should be {int}")]
fn then_exit_code(world: &mut MiddensWorld, expected: i32) {
    let actual = world.cli_exit_code.expect("no exit code recorded");
    assert_eq!(
        actual, expected,
        "expected exit code {expected}, got {actual}"
    );
}

fn files_with_extension(world: &MiddensWorld, extension: &str) -> Vec<PathBuf> {
    let output_dir = output_dir(world);
    let entries = fs::read_dir(&output_dir).unwrap_or_else(|error| {
        panic!(
            "failed to read analyze output directory {}: {}",
            output_dir.display(),
            error
        )
    });

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

fn read_file(path: &Path) -> String {
    fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", path.display(), error))
}

fn extract_frontmatter(markdown: &str) -> Option<String> {
    let mut lines = markdown.lines();
    if lines.next()? != "---" {
        return None;
    }

    let mut frontmatter = Vec::new();
    for line in lines {
        if line == "---" {
            return Some(frontmatter.join("\n"));
        }
        frontmatter.push(line.to_string());
    }

    None
}

fn parse_simple_yaml_map(frontmatter: &str) -> BTreeMap<String, String> {
    let mut map = BTreeMap::new();

    for line in frontmatter.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || line.starts_with(' ') || line.starts_with('\t') {
            continue;
        }

        let (key, value) = line
            .split_once(':')
            .unwrap_or_else(|| panic!("frontmatter line is not valid key/value YAML: {:?}", line));

        map.insert(key.trim().to_string(), value.trim().to_string());
    }

    map
}

fn corpus_size_from_markdown(path: &Path) -> u64 {
    let content = read_file(path);
    let frontmatter = extract_frontmatter(&content)
        .unwrap_or_else(|| panic!("markdown file {} is missing frontmatter", path.display()));
    let metadata = parse_simple_yaml_map(&frontmatter);
    let corpus_size = metadata.get("corpus_size").unwrap_or_else(|| {
        panic!(
            "markdown file {} is missing corpus_size in frontmatter",
            path.display()
        )
    });

    corpus_size.parse::<u64>().unwrap_or_else(|error| {
        panic!(
            "markdown file {} has non-numeric corpus_size {:?}: {}",
            path.display(),
            corpus_size,
            error
        )
    })
}

fn corpus_size_from_json(path: &Path) -> u64 {
    let content = read_file(path);
    let value: serde_json::Value = serde_json::from_str(&content)
        .unwrap_or_else(|error| panic!("json file {} is invalid: {}", path.display(), error));
    value["metadata"]["corpus_size"]
        .as_u64()
        .unwrap_or_else(|| {
            panic!(
                "json file {} is missing metadata.corpus_size",
                path.display()
            )
        })
}

// ---------------------------------------------------------------------------
// Given steps
// ---------------------------------------------------------------------------

#[given("a temporary analyze output directory")]
fn given_temporary_analyze_output_directory(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let output_dir = root.join("output");
    fs::create_dir_all(&output_dir).unwrap_or_else(|error| {
        panic!(
            "failed to create analyze output directory {}: {}",
            output_dir.display(),
            error
        )
    });
    world.output_path = Some(output_dir);
}

#[given("a missing analyze output directory")]
fn given_missing_analyze_output_directory(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let output_dir = root.join("missing-output").join("results");

    if output_dir.exists() {
        fs::remove_dir_all(&output_dir).unwrap_or_else(|error| {
            panic!(
                "failed to remove pre-existing analyze output directory {}: {}",
                output_dir.display(),
                error
            )
        });
    }

    world.output_path = Some(output_dir);
}

#[given("an empty temporary directory for analyze input")]
fn given_empty_analyze_input_directory(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let input_dir = root.join("input");
    fs::create_dir_all(&input_dir).unwrap_or_else(|error| {
        panic!(
            "failed to create empty analyze input directory {}: {}",
            input_dir.display(),
            error
        )
    });
}

// ---------------------------------------------------------------------------
// When steps
// ---------------------------------------------------------------------------

#[when("I run middens analyze on the fixtures directory")]
fn when_run_analyze_on_fixtures(world: &mut MiddensWorld) {
    run_analyze(world, &fixtures_dir(), false, None);
}

#[when("I run middens analyze on the temporary input directory")]
fn when_run_analyze_on_temporary_input(world: &mut MiddensWorld) {
    let input_dir = temp_root(world).join("input");
    run_analyze(world, &input_dir, false, None);
}

#[when("I run middens analyze on the fixtures directory with all techniques")]
fn when_run_analyze_on_fixtures_with_all(world: &mut MiddensWorld) {
    run_analyze(world, &fixtures_dir(), true, None);
}

#[when(expr = "I run middens analyze on the fixtures directory with techniques {string}")]
fn when_run_analyze_on_fixtures_with_subset(world: &mut MiddensWorld, techniques: String) {
    run_analyze(world, &fixtures_dir(), false, Some(&techniques));
}

// ---------------------------------------------------------------------------
// Then steps
// ---------------------------------------------------------------------------

#[then("the analyze output directory should exist")]
fn then_output_directory_exists(world: &mut MiddensWorld) {
    let output_dir = output_dir(world);
    assert!(
        output_dir.is_dir(),
        "analyze output directory does not exist: {}",
        output_dir.display()
    );
}

#[then(expr = "the analyze output directory should contain {int} markdown files")]
fn then_markdown_file_count(world: &mut MiddensWorld, expected: usize) {
    let files = files_with_extension(world, "md");
    assert_eq!(
        files.len(),
        expected,
        "expected {} markdown files, found {} in {}",
        expected,
        files.len(),
        output_dir(world).display()
    );
}

#[then(expr = "the analyze output directory should contain {int} JSON files")]
fn then_json_file_count(world: &mut MiddensWorld, expected: usize) {
    let files = files_with_extension(world, "json");
    assert_eq!(
        files.len(),
        expected,
        "expected {} JSON files, found {} in {}",
        expected,
        files.len(),
        output_dir(world).display()
    );
}

#[then(expr = "the analyze output should contain markdown and JSON files for techniques {string}")]
fn then_output_contains_files_for_techniques(world: &mut MiddensWorld, techniques: String) {
    let output_dir = output_dir(world);
    for technique in parse_techniques(&techniques) {
        let markdown = output_dir.join(format!("{technique}.md"));
        let json = output_dir.join(format!("{technique}.json"));

        assert!(
            markdown.is_file(),
            "missing markdown output for technique {} at {}",
            technique,
            markdown.display()
        );
        assert!(
            json.is_file(),
            "missing JSON output for technique {} at {}",
            technique,
            json.display()
        );
    }
}

#[then(expr = "every analyze output file should report corpus_size {int}")]
fn then_every_output_file_reports_corpus_size(world: &mut MiddensWorld, expected: i64) {
    let expected = expected as u64;
    let markdown_files = files_with_extension(world, "md");
    let json_files = files_with_extension(world, "json");

    assert!(
        !markdown_files.is_empty(),
        "expected markdown outputs before checking corpus_size"
    );
    assert!(
        !json_files.is_empty(),
        "expected JSON outputs before checking corpus_size"
    );

    for path in markdown_files {
        assert_eq!(
            corpus_size_from_markdown(&path),
            expected,
            "unexpected corpus_size in markdown file {}",
            path.display()
        );
    }

    for path in json_files {
        assert_eq!(
            corpus_size_from_json(&path),
            expected,
            "unexpected corpus_size in JSON file {}",
            path.display()
        );
    }
}

#[then("all markdown output files should have valid YAML frontmatter with corpus_size")]
fn then_markdown_files_have_frontmatter(world: &mut MiddensWorld) {
    let markdown_files = files_with_extension(world, "md");
    assert!(
        !markdown_files.is_empty(),
        "expected markdown output files to validate"
    );

    for path in markdown_files {
        let content = read_file(&path);
        let frontmatter = extract_frontmatter(&content)
            .unwrap_or_else(|| panic!("markdown file {} is missing frontmatter", path.display()));
        let metadata = parse_simple_yaml_map(&frontmatter);

        assert!(
            metadata.contains_key("technique"),
            "markdown file {} is missing technique frontmatter",
            path.display()
        );
        assert!(
            metadata.contains_key("generated_at"),
            "markdown file {} is missing generated_at frontmatter",
            path.display()
        );
        assert!(
            metadata.contains_key("middens_version"),
            "markdown file {} is missing middens_version frontmatter",
            path.display()
        );

        let corpus_size = metadata.get("corpus_size").unwrap_or_else(|| {
            panic!(
                "markdown file {} is missing corpus_size frontmatter",
                path.display()
            )
        });
        corpus_size.parse::<u64>().unwrap_or_else(|error| {
            panic!(
                "markdown file {} has non-numeric corpus_size {:?}: {}",
                path.display(),
                corpus_size,
                error
            )
        });
    }
}

#[then("all JSON output files should be valid JSON")]
fn then_json_files_are_valid(world: &mut MiddensWorld) {
    let json_files = files_with_extension(world, "json");
    assert!(
        !json_files.is_empty(),
        "expected JSON output files to validate"
    );

    for path in json_files {
        let content = read_file(&path);
        serde_json::from_str::<serde_json::Value>(&content)
            .unwrap_or_else(|error| panic!("json file {} is invalid: {}", path.display(), error));
    }
}

#[then(expr = "the analyze output file basenames should match technique names {string}")]
fn then_output_basenames_match(world: &mut MiddensWorld, techniques: String) {
    let expected: BTreeSet<String> = parse_techniques(&techniques).into_iter().collect();
    let markdown_names = basenames(&files_with_extension(world, "md"));
    let json_names = basenames(&files_with_extension(world, "json"));

    assert_eq!(
        markdown_names, expected,
        "markdown output basenames did not match expected technique names"
    );
    assert_eq!(
        json_names, expected,
        "JSON output basenames did not match expected technique names"
    );
}
