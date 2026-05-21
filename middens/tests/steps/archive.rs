use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};
use serde_json::Value;
use sha2::{Digest, Sha256};
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

fn set_named_path(world: &mut MiddensWorld, key: &str, path: PathBuf) {
    world.named_paths.insert(key.to_string(), path);
}

fn named_path(world: &MiddensWorld, key: &str) -> PathBuf {
    world
        .named_paths
        .get(key)
        .unwrap_or_else(|| panic!("missing named path <{}>", key))
        .clone()
}

fn expand_placeholders(world: &MiddensWorld, input: &str) -> String {
    let mut expanded = input.to_string();

    for (key, value) in &world.named_paths {
        let placeholder = format!("<{}>", key);
        expanded = expanded.replace(&placeholder, &value.to_string_lossy());
    }

    expanded
}

fn combined_output(world: &MiddensWorld) -> String {
    format!("{}\n{}", world.cli_output, world.cli_stderr)
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn sha256_file(path: &Path) -> String {
    let bytes = fs::read(path)
        .unwrap_or_else(|error| panic!("failed to read {} for hashing: {}", path.display(), error));
    sha256_hex(&bytes)
}

fn archive_object_path(archive_root: &Path, sha256: &str) -> PathBuf {
    archive_root
        .join("objects")
        .join("sha256")
        .join(&sha256[..2])
        .join(format!("{sha256}.jsonl"))
}

fn manifest_path(world: &MiddensWorld) -> PathBuf {
    named_path(world, "archive").join("manifest.json")
}

fn archive_index_path(world: &MiddensWorld) -> PathBuf {
    named_path(world, "archive")
        .join("indexes")
        .join("sessions.jsonl")
}

fn load_manifest(world: &MiddensWorld) -> Value {
    let path = manifest_path(world);
    let content = fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", path.display(), error));
    serde_json::from_str(&content)
        .unwrap_or_else(|error| panic!("failed to parse {}: {}", path.display(), error))
}

fn manifest_objects<'a>(manifest: &'a Value) -> &'a serde_json::Map<String, Value> {
    manifest["objects"]
        .as_object()
        .expect("manifest objects should be a JSON object")
}

fn manifest_observations<'a>(manifest: &'a Value) -> &'a Vec<Value> {
    manifest["observations"]
        .as_array()
        .expect("manifest observations should be a JSON array")
}

fn ensure_parent(path: &Path) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap_or_else(|error| {
            panic!("failed to create parent {}: {}", parent.display(), error)
        });
    }
}

fn copy_fixture_to(world: &mut MiddensWorld, fixture_name: &str, dest: &Path, label: &str) {
    let source = fixtures_dir().join(fixture_name);
    let bytes = fs::read(&source)
        .unwrap_or_else(|error| panic!("failed to read fixture {}: {}", source.display(), error));
    ensure_parent(dest);
    fs::write(dest, bytes)
        .unwrap_or_else(|error| panic!("failed to write fixture {}: {}", dest.display(), error));
    set_named_path(world, label, dest.to_path_buf());
    remember_value(world, &format!("source-before:{}", dest.display()), sha256_file(dest));
}

fn write_bytes(world: &mut MiddensWorld, dest: &Path, bytes: &[u8], label: &str) {
    ensure_parent(dest);
    fs::write(dest, bytes)
        .unwrap_or_else(|error| panic!("failed to write {}: {}", dest.display(), error));
    set_named_path(world, label, dest.to_path_buf());
    remember_value(world, &format!("source-before:{}", dest.display()), sha256_file(dest));
}

fn write_string(world: &mut MiddensWorld, dest: &Path, content: &str, label: &str) {
    write_bytes(world, dest, content.as_bytes(), label);
}

fn remember_value(world: &mut MiddensWorld, key: &str, value: String) {
    world.remembered_values.insert(key.to_string(), value);
}

fn remembered_value<'a>(world: &'a MiddensWorld, key: &str) -> &'a str {
    world
        .remembered_values
        .get(key)
        .unwrap_or_else(|| panic!("missing remembered value {}", key))
}

fn archive_observation_by_basename<'a>(manifest: &'a Value, basename: &str) -> &'a Value {
    manifest_observations(manifest)
        .iter()
        .find(|obs| obs["original_basename"].as_str() == Some(basename))
        .unwrap_or_else(|| panic!("no observation with basename {}", basename))
}

fn archive_object_for_label(world: &MiddensWorld, label: &str) -> PathBuf {
    let source = named_path(world, label);
    let sha256 = sha256_file(&source);
    archive_object_path(&named_path(world, "archive"), &sha256)
}

fn archive_object_for_remembered_sha(world: &MiddensWorld, key: &str) -> PathBuf {
    archive_object_path(&named_path(world, "archive"), remembered_value(world, key))
}

fn create_default_home_fixture(world: &mut MiddensWorld, tool: &str, fixture_name: &str, label: &str) {
    let home = named_path(world, "home");
    let dest = match tool {
        "claude-code" => home
            .join(".claude")
            .join("projects")
            .join("demo-project")
            .join("claude-default.jsonl"),
        "codex" => home
            .join(".codex")
            .join("sessions")
            .join("2026")
            .join("03")
            .join("01")
            .join("codex-default.jsonl"),
        other => panic!("unsupported default-home fixture tool {}", other),
    };
    copy_fixture_to(world, fixture_name, &dest, label);
}

fn run_archive(world: &mut MiddensWorld, args: &str) {
    let expanded = expand_placeholders(world, args);
    let arg_list: Vec<String> = expanded.split_whitespace().map(ToOwned::to_owned).collect();

    let mut command = Command::new(middens_bin());
    command.arg("archive").args(&arg_list);

    if let Some(home) = world.named_paths.get("home") {
        command.env("HOME", home);
    }

    for (key, value) in &world.env_vars {
        command.env(key, value);
    }

    let output = command
        .output()
        .expect("failed to execute middens archive binary");

    world.cli_output = String::from_utf8_lossy(&output.stdout).to_string();
    world.cli_stderr = String::from_utf8_lossy(&output.stderr).to_string();
    world.cli_exit_code = output.status.code();
}

fn json_contains_string(value: &Value, needle: &str) -> bool {
    match value {
        Value::String(s) => s.contains(needle),
        Value::Array(items) => items.iter().any(|item| json_contains_string(item, needle)),
        Value::Object(map) => map.values().any(|item| json_contains_string(item, needle)),
        _ => false,
    }
}

fn source_file_paths(world: &MiddensWorld) -> Vec<PathBuf> {
    let mut paths: Vec<PathBuf> = world
        .named_paths
        .iter()
        .filter(|(key, _)| {
            key.starts_with("claude_")
                || key.starts_with("codex_")
                || key.starts_with("unparseable_")
                || key.starts_with("parser_error_")
        })
        .map(|(_, path)| path.clone())
        .collect();
    paths.sort();
    paths.dedup();
    paths
}

#[given("a temporary archive sandbox")]
fn given_temporary_archive_sandbox(world: &mut MiddensWorld) {
    let root = temp_root(world);
    let home = root.join("home");
    let workspace = root.join("workspace");
    let archive = root.join("archive");
    let claude_source = root.join("sources").join("claude");
    let codex_source = root.join("sources").join("codex");
    let missing_source = root.join("sources").join("missing");

    fs::create_dir_all(&home).expect("failed to create sandbox home");
    fs::create_dir_all(&workspace).expect("failed to create sandbox workspace");

    set_named_path(world, "home", home);
    set_named_path(world, "workspace", workspace);
    set_named_path(world, "archive", archive);
    set_named_path(world, "claude_source", claude_source);
    set_named_path(world, "codex_source", codex_source);
    set_named_path(world, "missing_source", missing_source);
}

#[given("the archive root path does not exist")]
fn given_archive_root_missing(world: &mut MiddensWorld) {
    let archive = named_path(world, "archive");
    if archive.exists() {
        fs::remove_dir_all(&archive)
            .unwrap_or_else(|error| panic!("failed to remove {}: {}", archive.display(), error));
    }
}

#[given("an explicit Claude source root containing one parseable session")]
fn given_explicit_claude_source(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    let session = source_root.join("project-a").join("claude-primary.jsonl");
    copy_fixture_to(world, "claude_code_sample.jsonl", &session, "claude_primary");
}

#[given("an explicit Claude source root containing two identical sessions")]
fn given_explicit_claude_duplicates(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    let first = source_root.join("team-a").join("claude-duplicate-a.jsonl");
    let second = source_root.join("team-b").join("claude-duplicate-b.jsonl");
    copy_fixture_to(world, "claude_code_sample.jsonl", &first, "claude_primary");

    let bytes = fs::read(named_path(world, "claude_primary"))
        .expect("failed to re-read primary duplicate fixture");
    write_bytes(world, &second, &bytes, "claude_duplicate");
}

#[given("an explicit Claude source root containing one unparseable JSONL file")]
fn given_explicit_unparseable_source(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    let file = source_root.join("mystery").join("unparseable-session.jsonl");
    write_string(
        world,
        &file,
        "{\"kind\":\"mystery\",\"payload\":\"valid json but no known parser\"}\n",
        "unparseable_file",
    );
}

#[given("an explicit Claude source root containing one parser-error Claude fixture")]
fn given_explicit_parser_error_source(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    let file = source_root.join("broken").join("claude-parser-error.jsonl");
    let content = concat!(
        "{\"parentUuid\":null,\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"hello\"},\"uuid\":\"ok-1\",\"timestamp\":\"2026-03-19T14:30:02.320Z\",\"sessionId\":\"broken-session\",\"version\":\"2.1.76\"}\n",
        "LEAK_ME_SECRET_PAYLOAD\n"
    );
    write_string(world, &file, content, "parser_error_file");
}

#[given("the sandbox home contains one default Claude session and one default Codex session")]
fn given_default_claude_and_codex(world: &mut MiddensWorld) {
    create_default_home_fixture(world, "claude-code", "claude_code_sample.jsonl", "claude_default");
    create_default_home_fixture(world, "codex", "codex_sample.jsonl", "codex_default");
}

#[given("the explicit source path does not exist")]
fn given_missing_explicit_source_path(_world: &mut MiddensWorld) {}

#[given("an unreadable explicit Claude source root")]
fn given_unreadable_source(world: &mut MiddensWorld) {
    given_explicit_claude_source(world);

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;

        let source_root = named_path(world, "claude_source");
        fs::set_permissions(&source_root, fs::Permissions::from_mode(0o000)).unwrap_or_else(
            |error| {
                panic!(
                    "failed to chmod unreadable source root {}: {}",
                    source_root.display(),
                    error
                )
            },
        );
    }

    #[cfg(not(unix))]
    panic!("unreadable-source archive scenario currently requires a Unix test host");
}

#[given("an explicit Claude source root containing a symlinked session")]
fn given_symlinked_source(world: &mut MiddensWorld) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;

        let source_root = named_path(world, "claude_source");
        let target = source_root.join("targets").join("claude-target.jsonl");
        let link = source_root.join("links").join("claude-symlink.jsonl");

        copy_fixture_to(world, "claude_code_sample.jsonl", &target, "claude_symlink_target");
        ensure_parent(&link);
        symlink(&target, &link)
            .unwrap_or_else(|error| panic!("failed to create symlink {}: {}", link.display(), error));
        set_named_path(world, "claude_symlink", link);
    }

    #[cfg(not(unix))]
    panic!("symlink archive scenarios currently require a Unix test host");
}

#[given("an explicit Claude source root containing a symlink loop")]
fn given_symlink_loop_source(world: &mut MiddensWorld) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;

        let source_root = named_path(world, "claude_source");
        fs::create_dir_all(&source_root).expect("failed to create symlink-loop source root");
        let loop_link = source_root.join("loop");
        symlink(&source_root, &loop_link).unwrap_or_else(|error| {
            panic!("failed to create symlink loop {}: {}", loop_link.display(), error)
        });
        set_named_path(world, "claude_loop", loop_link);
    }

    #[cfg(not(unix))]
    panic!("symlink-loop archive scenarios currently require a Unix test host");
}

#[given("the archive root is inside a git worktree")]
fn given_archive_inside_git_worktree(world: &mut MiddensWorld) {
    let workspace = named_path(world, "workspace");
    let git_dir = workspace.join(".git");
    let archive = workspace.join("private").join("archive");

    fs::create_dir_all(&git_dir)
        .unwrap_or_else(|error| panic!("failed to create {}: {}", git_dir.display(), error));
    set_named_path(world, "archive", archive);
}

#[given("the archive root already has a user-authored .gitignore")]
fn given_archive_has_user_gitignore(world: &mut MiddensWorld) {
    let gitignore = named_path(world, "archive").join(".gitignore");
    ensure_parent(&gitignore);
    fs::write(&gitignore, "# keep me\n*.tmp\n").unwrap_or_else(|error| {
        panic!("failed to write archive .gitignore {}: {}", gitignore.display(), error)
    });
    remember_value(
        world,
        "archive_gitignore_before",
        fs::read_to_string(&gitignore).expect("failed to re-read archive .gitignore"),
    );
}

#[given("the archive root contains a corrupt manifest")]
fn given_corrupt_manifest(world: &mut MiddensWorld) {
    let manifest = manifest_path(world);
    ensure_parent(&manifest);
    fs::write(&manifest, "{not valid json").unwrap_or_else(|error| {
        panic!("failed to write corrupt manifest {}: {}", manifest.display(), error)
    });
}

#[given("the archive lock file already exists")]
fn given_archive_lock(world: &mut MiddensWorld) {
    let lock_path = named_path(world, "archive").join(".archive.lock");
    ensure_parent(&lock_path);
    fs::write(&lock_path, "locked\n").unwrap_or_else(|error| {
        panic!("failed to write archive lock {}: {}", lock_path.display(), error)
    });
}

#[given(expr = "the archive root contains a destination collision for {string}")]
fn given_destination_collision(world: &mut MiddensWorld, label: String) {
    let source = named_path(world, &label);
    let sha256 = sha256_file(&source);
    let collision_path = archive_object_path(&named_path(world, "archive"), &sha256);
    ensure_parent(&collision_path);
    fs::write(&collision_path, b"not the bytes that match the hash\n").unwrap_or_else(|error| {
        panic!(
            "failed to write collision fixture {}: {}",
            collision_path.display(),
            error
        )
    });
}

#[given(expr = "archive write hook {string} is enabled")]
fn given_archive_write_hook(world: &mut MiddensWorld, hook_name: String) {
    world
        .env_vars
        .insert("MIDDENS_ARCHIVE_TEST_HOOK".to_string(), hook_name);
}

#[given("the archive root equals the explicit Claude source root")]
fn given_archive_root_equals_source(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    set_named_path(world, "archive", source_root);
}

#[given("the archive root is inside the explicit Claude source root")]
fn given_archive_root_inside_source(world: &mut MiddensWorld) {
    let source_root = named_path(world, "claude_source");
    set_named_path(world, "archive", source_root.join("nested-archive"));
}

#[given("the archive root is an ancestor of the explicit Claude source root")]
fn given_archive_root_ancestor_of_source(world: &mut MiddensWorld) {
    let root = temp_root(world).join("shared-root");
    let source = root.join("source");
    let previous_source = named_path(world, "claude_source");

    if previous_source.exists() && previous_source != source {
        ensure_parent(&source);
        fs::rename(&previous_source, &source).unwrap_or_else(|error| {
            panic!(
                "failed to move source root from {} to {}: {}",
                previous_source.display(),
                source.display(),
                error
            )
        });
    }

    set_named_path(world, "archive", root.clone());
    set_named_path(world, "claude_source", source);
}

#[when(expr = "I run middens archive with arguments {string}")]
fn when_run_archive(world: &mut MiddensWorld, args: String) {
    run_archive(world, &args);
}

#[when(expr = "I remember the source file hash for {string}")]
fn when_remember_source_hash(world: &mut MiddensWorld, label: String) {
    let path = named_path(world, &label);
    remember_value(world, &format!("{label}_source_sha_before"), sha256_file(&path));
}

#[when(expr = "I remember the archived object bytes for {string}")]
fn when_remember_archived_object_bytes(world: &mut MiddensWorld, label: String) {
    let object_path = archive_object_for_label(world, &label);
    let bytes = fs::read(&object_path).unwrap_or_else(|error| {
        panic!(
            "failed to read archived object {}: {}",
            object_path.display(),
            error
        )
    });
    remember_value(
        world,
        &format!("{label}_archived_bytes_sha"),
        sha256_hex(&bytes),
    );
}

#[when(expr = "I replace the {string} source file with a different parseable Claude fixture")]
fn when_replace_source_with_different_claude_fixture(world: &mut MiddensWorld, label: String) {
    let path = named_path(world, &label);
    let source = fixtures_dir().join("claude_code_sample.jsonl");
    let content = fs::read_to_string(&source)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", source.display(), error))
        .replace("test-session-001", "test-session-002")
        .replace("Hello world", "Goodbye world");

    fs::write(&path, content)
        .unwrap_or_else(|error| panic!("failed to overwrite {}: {}", path.display(), error));
}

#[when(expr = "I delete the archived object for {string}")]
fn when_delete_archived_object(world: &mut MiddensWorld, label: String) {
    let object_path = archive_object_for_label(world, &label);
    fs::remove_file(&object_path).unwrap_or_else(|error| {
        panic!(
            "failed to remove archived object {}: {}",
            object_path.display(),
            error
        )
    });
}

#[then("the archive root should not exist")]
fn then_archive_root_should_not_exist(world: &mut MiddensWorld) {
    let archive = named_path(world, "archive");
    assert!(
        !archive.exists(),
        "archive root should not exist, but {} is present",
        archive.display()
    );
}

#[then(expr = "the combined archive output should contain {string}")]
fn then_combined_output_contains(world: &mut MiddensWorld, text: String) {
    let expected = expand_placeholders(world, &text);
    let combined = combined_output(world);
    assert!(
        combined.contains(&expected),
        "expected combined output to contain {:?}, got:\n{}",
        expected,
        combined
    );
}

#[then(expr = "the combined archive output should not contain {string}")]
fn then_combined_output_not_contains(world: &mut MiddensWorld, text: String) {
    let forbidden = expand_placeholders(world, &text);
    let combined = combined_output(world);
    assert!(
        !combined.contains(&forbidden),
        "expected combined output not to contain {:?}, got:\n{}",
        forbidden,
        combined
    );
}

#[then(expr = "the archive object for {string} should match the source bytes")]
fn then_archive_object_matches_source(world: &mut MiddensWorld, label: String) {
    let source = named_path(world, &label);
    let expected_sha = sha256_file(&source);
    let archive_object = archive_object_path(&named_path(world, "archive"), &expected_sha);

    assert!(
        archive_object.is_file(),
        "expected archive object at {}",
        archive_object.display()
    );
    assert_eq!(
        fs::read(&source).expect("failed to read source bytes"),
        fs::read(&archive_object).expect("failed to read archived bytes"),
        "archived object bytes do not match source {}",
        source.display()
    );
}

#[then("the archive manifest should satisfy the required schema minimums")]
fn then_manifest_schema_minimums(world: &mut MiddensWorld) {
    let manifest = load_manifest(world);

    for key in [
        "archive_manifest_version",
        "created_at",
        "updated_at",
        "middens_version",
        "archive_root",
        "objects",
        "observations",
    ] {
        assert!(
            manifest.get(key).is_some(),
            "manifest is missing top-level key {}",
            key
        );
    }

    let object = manifest_objects(&manifest)
        .values()
        .next()
        .expect("manifest should contain at least one archived object");
    for key in [
        "sha256",
        "size_bytes",
        "archive_path",
        "first_archived_at",
        "parser_status",
        "source_tool",
        "session_count",
        "session_ids",
        "first_timestamp",
        "last_timestamp",
    ] {
        assert!(
            object.get(key).is_some(),
            "archived object is missing key {}",
            key
        );
    }

    let observation = manifest_observations(&manifest)
        .first()
        .expect("manifest should contain at least one observation");
    for key in [
        "observation_id",
        "source_tool",
        "original_path",
        "canonical_path",
        "original_basename",
        "archive_path",
        "sha256",
        "size_bytes",
        "source_mtime",
        "observed_at",
    ] {
        assert!(
            observation.get(key).is_some(),
            "observation is missing key {}",
            key
        );
    }
}

#[then(expr = "the archive manifest should contain {int} object and {int} observation")]
fn then_manifest_counts(world: &mut MiddensWorld, object_count: usize, observation_count: usize) {
    let manifest = load_manifest(world);
    assert_eq!(
        manifest_objects(&manifest).len(),
        object_count,
        "unexpected manifest object count"
    );
    assert_eq!(
        manifest_observations(&manifest).len(),
        observation_count,
        "unexpected manifest observation count"
    );
}

#[then("the archive index should reference a manifest object hash")]
fn then_archive_index_references_manifest_hash(world: &mut MiddensWorld) {
    let manifest = load_manifest(world);
    let manifest_hashes: Vec<String> = manifest_objects(&manifest).keys().cloned().collect();
    let index_path = archive_index_path(world);

    assert!(index_path.is_file(), "missing archive index {}", index_path.display());

    let content = fs::read_to_string(&index_path)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", index_path.display(), error));
    let mut saw_record = false;
    let mut saw_hash_reference = false;

    for line in content.lines().filter(|line| !line.trim().is_empty()) {
        saw_record = true;
        let value: Value = serde_json::from_str(line)
            .unwrap_or_else(|error| panic!("invalid index JSONL line {:?}: {}", line, error));
        if manifest_hashes
            .iter()
            .any(|sha| json_contains_string(&value, sha))
        {
            saw_hash_reference = true;
            break;
        }
    }

    assert!(saw_record, "archive index should contain at least one JSONL record");
    assert!(
        saw_hash_reference,
        "archive index should reference at least one manifest object hash"
    );
}

#[then("the source fixture files should be unchanged")]
fn then_source_files_unchanged(world: &mut MiddensWorld) {
    for path in source_file_paths(world) {
        let key = format!("source-before:{}", path.display());
        let current_sha = sha256_file(&path);
        let original_sha = world.remembered_values.entry(key.clone()).or_insert(current_sha.clone());
        assert_eq!(
            original_sha, &current_sha,
            "source fixture changed unexpectedly: {}",
            path.display()
        );
    }
}

#[then(expr = "the remembered archived object bytes for {string} should be unchanged")]
fn then_archived_object_bytes_unchanged(world: &mut MiddensWorld, label: String) {
    let object_path = archive_object_for_label(world, &label);
    let current = sha256_file(&object_path);
    let remembered = remembered_value(world, &format!("{label}_archived_bytes_sha"));
    assert_eq!(
        current, remembered,
        "archived object bytes changed for {}",
        object_path.display()
    );
}

#[then("all archive observations should point to the same archive path")]
fn then_all_observations_share_archive_path(world: &mut MiddensWorld) {
    let manifest = load_manifest(world);
    let observations = manifest_observations(&manifest);
    let first = observations
        .first()
        .and_then(|obs| obs["archive_path"].as_str())
        .expect("first observation missing archive_path");

    for observation in observations {
        assert_eq!(
            observation["archive_path"].as_str(),
            Some(first),
            "not all observations point at the same archive_path"
        );
    }
}

#[then("both archived object files for the changed source should exist")]
fn then_both_changed_source_objects_exist(world: &mut MiddensWorld) {
    let old_path = archive_object_for_remembered_sha(world, "claude_primary_source_sha_before");
    let new_path = archive_object_for_label(world, "claude_primary");

    assert!(old_path.is_file(), "missing original archived object {}", old_path.display());
    assert!(new_path.is_file(), "missing updated archived object {}", new_path.display());
}

#[then("manifest.json should not exist under the archive root")]
fn then_manifest_should_not_exist(world: &mut MiddensWorld) {
    let manifest = manifest_path(world);
    assert!(
        !manifest.exists(),
        "manifest.json should not exist, but {} is present",
        manifest.display()
    );
}

#[then(expr = "the archive manifest should record parser status {string}")]
fn then_manifest_parser_status(world: &mut MiddensWorld, expected: String) {
    let manifest = load_manifest(world);
    let object = manifest_objects(&manifest)
        .values()
        .next()
        .expect("manifest should contain an object");
    assert_eq!(
        object["parser_status"].as_str(),
        Some(expected.as_str()),
        "unexpected parser_status"
    );
}

#[then(expr = "the parser diagnostic should not contain {string}")]
fn then_parser_diagnostic_not_contains(world: &mut MiddensWorld, forbidden: String) {
    let manifest = load_manifest(world);
    let object = manifest_objects(&manifest)
        .values()
        .next()
        .expect("manifest should contain an object");
    let diagnostic = object["parser_error"]
        .as_str()
        .expect("parser_error should be a string for parser-error scenario");
    assert!(
        !diagnostic.contains(&forbidden),
        "parser diagnostic leaked forbidden payload {:?}: {}",
        forbidden,
        diagnostic
    );
}

#[then("the parser diagnostic should be non-empty")]
fn then_parser_diagnostic_non_empty(world: &mut MiddensWorld) {
    let manifest = load_manifest(world);
    let object = manifest_objects(&manifest)
        .values()
        .next()
        .expect("manifest should contain an object");
    let diagnostic = object["parser_error"]
        .as_str()
        .expect("parser_error should be a string");
    assert!(
        !diagnostic.trim().is_empty(),
        "parser_error diagnostic should not be empty"
    );
}

#[then(expr = "all archive observations should have source tool {string}")]
fn then_all_observations_have_source_tool(world: &mut MiddensWorld, expected: String) {
    let manifest = load_manifest(world);
    for observation in manifest_observations(&manifest) {
        assert_eq!(
            observation["source_tool"].as_str(),
            Some(expected.as_str()),
            "unexpected source_tool in observation"
        );
    }
}

#[then(expr = "no archive observation should have basename {string}")]
fn then_no_observation_has_basename(world: &mut MiddensWorld, basename: String) {
    let manifest = load_manifest(world);
    assert!(
        manifest_observations(&manifest)
            .iter()
            .all(|obs| obs["original_basename"].as_str() != Some(basename.as_str())),
        "unexpected observation basename {} present in manifest",
        basename
    );
}

#[then(expr = "the archive observation for basename {string} should record canonical path {string}")]
fn then_observation_records_canonical_path(
    world: &mut MiddensWorld,
    basename: String,
    expected_path: String,
) {
    let manifest = load_manifest(world);
    let observation = archive_observation_by_basename(&manifest, &basename);
    let expected = expand_placeholders(world, &expected_path);
    assert_eq!(
        observation["canonical_path"].as_str(),
        Some(expected.as_str()),
        "unexpected canonical_path for observation {}",
        basename
    );
}

#[then(expr = "the final archive object for {string} should not exist")]
fn then_final_archive_object_missing(world: &mut MiddensWorld, label: String) {
    let object_path = archive_object_for_label(world, &label);
    assert!(
        !object_path.exists(),
        "final archive object should not exist after interrupted copy: {}",
        object_path.display()
    );
}

#[then("manifest.json should be absent or valid JSON")]
fn then_manifest_absent_or_valid_json(world: &mut MiddensWorld) {
    let manifest = manifest_path(world);
    if !manifest.exists() {
        return;
    }

    let content = fs::read_to_string(&manifest)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", manifest.display(), error));
    serde_json::from_str::<Value>(&content).unwrap_or_else(|error| {
        panic!(
            "manifest should be absent or valid JSON, but {} failed to parse: {}",
            manifest.display(),
            error
        )
    });
}

#[then("the archive .gitignore should deny all contents")]
fn then_archive_gitignore_deny_all(world: &mut MiddensWorld) {
    let gitignore = named_path(world, "archive").join(".gitignore");
    let content = fs::read_to_string(&gitignore)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", gitignore.display(), error));
    assert_eq!(content, "*\n!.gitignore\n", "unexpected archive .gitignore contents");
}

#[then("the archive .gitignore should remain unchanged")]
fn then_archive_gitignore_unchanged(world: &mut MiddensWorld) {
    let gitignore = named_path(world, "archive").join(".gitignore");
    let current = fs::read_to_string(&gitignore)
        .unwrap_or_else(|error| panic!("failed to read {}: {}", gitignore.display(), error));
    let original = remembered_value(world, "archive_gitignore_before");
    assert_eq!(current, original, "archive .gitignore was unexpectedly modified");
}
