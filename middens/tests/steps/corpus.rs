use std::fs;
use std::path::Path;

use cucumber::{given, then, when};
use tempfile::TempDir;

use middens::corpus::discovery::discover_sessions;
use middens::corpus::manifest::{create_manifest, hash_file, Manifest};

use super::world::MiddensWorld;

// ---------------------------------------------------------------------------
// Givens
// ---------------------------------------------------------------------------

#[given("a temporary directory with nested structure")]
fn tmp_dir_with_nested_structure(world: &mut MiddensWorld) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    let sub = tmp.path().join("nested").join("deep");
    fs::create_dir_all(&sub).expect("failed to create nested dirs");
    world.temp_dir = Some(tmp);
}

#[given(expr = "a temporary directory with a {string} subdirectory")]
fn tmp_dir_with_subdirectory(world: &mut MiddensWorld, subdir: String) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    let sub = tmp.path().join(&subdir);
    fs::create_dir_all(&sub).expect("failed to create subdirectory");
    world.temp_dir = Some(tmp);
}

#[given("a temporary directory")]
fn tmp_dir(world: &mut MiddensWorld) {
    let tmp = TempDir::new().expect("failed to create temp dir");
    world.temp_dir = Some(tmp);
}

#[given(expr = "a file {string} at the root with content {string}")]
fn file_at_root(world: &mut MiddensWorld, filename: String, content: String) {
    let tmp = world.temp_dir.as_ref().expect("temp_dir not set");
    let path = tmp.path().join(&filename);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("failed to create parent dirs");
    }
    fs::write(&path, &content).expect("failed to write file");
}

#[given(expr = "a file {string} with content {string}")]
fn file_with_content(world: &mut MiddensWorld, rel_path: String, content: String) {
    let tmp = world.temp_dir.as_ref().expect("temp_dir not set");
    let path = tmp.path().join(&rel_path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("failed to create parent dirs");
    }
    fs::write(&path, &content).expect("failed to write file");
}

// ---------------------------------------------------------------------------
// Whens
// ---------------------------------------------------------------------------

#[when("I run corpus discovery on the temporary directory")]
fn run_discovery(world: &mut MiddensWorld) {
    let tmp = world.temp_dir.as_ref().expect("temp_dir not set");
    let found = discover_sessions(Some(tmp.path())).expect("discovery failed");
    world.discovered_files = found;
}

#[when("I run corpus discovery on a non-existent directory")]
fn run_discovery_missing(world: &mut MiddensWorld) {
    let found = discover_sessions(Some(Path::new("/tmp/nonexistent-middens-test-dir")))
        .expect("discovery should not error on missing dir");
    world.discovered_files = found;
}

#[when(expr = "I create a manifest of the {string} subdirectory")]
fn create_manifest_step(world: &mut MiddensWorld, subdir: String) {
    let tmp = world.temp_dir.as_ref().expect("temp_dir not set");
    let corpus_path = tmp.path().join(&subdir);
    let output = tmp.path().join("manifest.json");
    create_manifest(&corpus_path, &output).expect("create_manifest failed");
    world.output_path = Some(output);
}

#[when(expr = "I hash the file {string} twice")]
fn hash_file_twice(world: &mut MiddensWorld, filename: String) {
    let tmp = world.temp_dir.as_ref().expect("temp_dir not set");
    let file_path = tmp.path().join(&filename);

    let h1 = hash_file(&file_path).expect("first hash failed");
    let h2 = hash_file(&file_path).expect("second hash failed");

    // Store both hashes in cli_output and cli_stderr as convenient scratch fields.
    world.cli_output = h1;
    world.cli_stderr = h2;
}

// ---------------------------------------------------------------------------
// Thens
// ---------------------------------------------------------------------------

#[then(expr = "{int} session files should be discovered")]
fn check_discovered_count(world: &mut MiddensWorld, expected: usize) {
    assert_eq!(
        world.discovered_files.len(),
        expected,
        "expected {} discovered files, got {}",
        expected,
        world.discovered_files.len()
    );
}

#[then(expr = "all discovered files should have the {string} extension")]
fn all_files_have_extension(world: &mut MiddensWorld, ext: String) {
    let ext_no_dot = ext.trim_start_matches('.');
    for path in &world.discovered_files {
        let actual = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("<none>");
        assert_eq!(
            actual, ext_no_dot,
            "file {} has extension {:?}, expected {}",
            path.display(),
            actual,
            ext_no_dot
        );
    }
}

#[then(expr = "the manifest should contain {int} entry")]
fn manifest_entry_count(world: &mut MiddensWorld, expected: usize) {
    let output = world.output_path.as_ref().expect("output_path not set");
    let content = fs::read_to_string(output).expect("failed to read manifest");
    let manifest: Manifest = serde_json::from_str(&content).expect("failed to parse manifest");
    assert_eq!(
        manifest.entries.len(),
        expected,
        "expected {} manifest entries, got {}",
        expected,
        manifest.entries.len()
    );
}

#[then(expr = "the manifest entry path should end with {string}")]
fn manifest_entry_path_ends_with(world: &mut MiddensWorld, suffix: String) {
    let output = world.output_path.as_ref().expect("output_path not set");
    let content = fs::read_to_string(output).expect("failed to read manifest");
    let manifest: Manifest = serde_json::from_str(&content).expect("failed to parse manifest");
    assert!(
        manifest.entries[0].path.ends_with(&suffix),
        "manifest entry path {:?} does not end with {:?}",
        manifest.entries[0].path,
        suffix
    );
}

#[then(expr = "the manifest entry size should be greater than {int}")]
fn manifest_entry_size_gt(world: &mut MiddensWorld, min: u64) {
    let output = world.output_path.as_ref().expect("output_path not set");
    let content = fs::read_to_string(output).expect("failed to read manifest");
    let manifest: Manifest = serde_json::from_str(&content).expect("failed to parse manifest");
    assert!(
        manifest.entries[0].size > min,
        "expected size > {}, got {}",
        min, manifest.entries[0].size
    );
}

#[then("the manifest entry sha256 should not be empty")]
fn manifest_entry_sha256_not_empty(world: &mut MiddensWorld) {
    let output = world.output_path.as_ref().expect("output_path not set");
    let content = fs::read_to_string(output).expect("failed to read manifest");
    let manifest: Manifest = serde_json::from_str(&content).expect("failed to parse manifest");
    assert!(
        !manifest.entries[0].sha256.is_empty(),
        "manifest entry sha256 should not be empty"
    );
}

#[then("both hashes should be identical")]
fn hashes_identical(world: &mut MiddensWorld) {
    assert_eq!(
        world.cli_output, world.cli_stderr,
        "expected identical hashes, got {:?} and {:?}",
        world.cli_output, world.cli_stderr
    );
}
