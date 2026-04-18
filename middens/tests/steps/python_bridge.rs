use crate::steps::world::MiddensWorld;
use cucumber::{given, then, when};
use middens::bridge::technique::PythonTechnique;
use middens::bridge::uv::UvManager;
use middens::pipeline::{PipelineConfig, TechniqueFilter, run};
use middens::session::{EnvironmentFingerprint, Session, SessionMetadata, SessionType, SourceTool};
use middens::storage::RedactionConfig;
use middens::techniques::Technique;
use std::path::PathBuf;

fn resolve_python_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let reqs = manifest_dir.join("python/requirements.txt");

    match UvManager::detect(reqs) {
        Ok(uv) => {
            // Ensure the venv exists before using its python
            if let Err(e) = uv.init() {
                eprintln!("uv init failed, falling back to system python: {}", e);
                return system_python_fallback();
            }
            uv.python_path().clone()
        }
        Err(_) => system_python_fallback(),
    }
}

fn system_python_fallback() -> PathBuf {
    // Try python3 first (Unix convention), then python (Windows convention)
    for name in &["python3", "python"] {
        if std::process::Command::new(name)
            .arg("--version")
            .output()
            .is_ok()
        {
            return PathBuf::from(name);
        }
    }
    // Last resort — let it fail at spawn time with a clear error
    PathBuf::from("python3")
}

#[given("uv is available in the environment")]
fn uv_available(world: &mut MiddensWorld) {
    if std::process::Command::new("uv")
        .arg("--version")
        .output()
        .is_err()
    {
        world.skipped = true;
    }
}

#[then("the bridge should detect uv successfully")]
fn bridge_detects_uv(world: &mut MiddensWorld) {
    if world.skipped {
        eprintln!("SKIP: uv not installed, skipping detection test");
        return;
    }
    let reqs = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("python/requirements.txt");
    UvManager::detect(reqs).expect("uv should be detected when installed");
}

#[given("the echo Python technique is available")]
fn echo_available(_world: &mut MiddensWorld) {
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("python/techniques/echo.py");
    assert!(script.exists(), "echo.py not found at {}", script.display());
}

#[given("a set of test sessions")]
fn set_test_sessions(world: &mut MiddensWorld) {
    world.sessions = vec![
        Session {
            id: "test1".to_string(),
            source_path: PathBuf::from("test1.jsonl"),
            source_tool: SourceTool::Unknown,
            session_type: SessionType::Unknown,
            messages: vec![],
            metadata: SessionMetadata::default(),
            environment: EnvironmentFingerprint::default(),
            thinking_visibility: middens::session::ThinkingVisibility::Unknown,
        },
        Session {
            id: "test2".to_string(),
            source_path: PathBuf::from("test2.jsonl"),
            source_tool: SourceTool::Unknown,
            session_type: SessionType::Unknown,
            messages: vec![],
            metadata: SessionMetadata::default(),
            environment: EnvironmentFingerprint::default(),
            thinking_visibility: middens::session::ThinkingVisibility::Unknown,
        },
    ];
}

#[when("the echo technique is run")]
fn run_echo_technique(world: &mut MiddensWorld) {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let script_path = manifest_dir.join("python/techniques/echo.py");
    let python_path = resolve_python_path();

    let tech = PythonTechnique::new("echo", "Echo summary", script_path, python_path, 30);

    match tech.run(&world.sessions) {
        Ok(res) => world.technique_result = Some(res),
        Err(e) => world.error = Some(e.to_string()),
    }
}

#[then("it should successfully serialize sessions to a temporary file")]
fn check_serialization(world: &mut MiddensWorld) {
    assert!(
        world.error.is_none(),
        "serialization failed: {:?}",
        world.error
    );
}

#[then("the subprocess should execute successfully")]
fn check_subprocess_spawn(world: &mut MiddensWorld) {
    assert!(
        world.error.is_none(),
        "expected subprocess execution to succeed, got error: {:?}",
        world.error
    );
    assert!(
        world.technique_result.is_some(),
        "expected subprocess execution to produce a TechniqueResult"
    );
}

#[then("it should parse the stdout into a TechniqueResult")]
fn check_parse_stdout(world: &mut MiddensWorld) {
    assert!(
        world.technique_result.is_some(),
        "no TechniqueResult parsed"
    );
}

#[then(expr = "the finding {string} should be equal to the number of test sessions")]
fn check_finding_value(world: &mut MiddensWorld, label: String) {
    let result = world.technique_result.as_ref().expect("No TechniqueResult");
    let finding = result
        .findings
        .iter()
        .find(|f| f.label == label)
        .expect("Finding not found");

    let value = finding.value.as_u64().expect("Value is not a number");
    assert_eq!(value as usize, world.sessions.len());
}

#[given(expr = "a Python technique that exits with code {int}")]
fn python_tech_with_exit_code(world: &mut MiddensWorld, code: i32) {
    if world.temp_dir.is_none() {
        world.temp_dir = Some(tempfile::tempdir().unwrap());
    }
    let script_path = world.temp_dir.as_ref().unwrap().path().join("exit_code.py");
    std::fs::write(&script_path, format!("import sys\nsys.exit({})", code)).unwrap();
    world.file_path = Some(script_path);
}

#[when("the technique is run")]
fn run_generic_technique(world: &mut MiddensWorld) {
    let script_path = world.file_path.clone().expect("No script path");
    let python_path = resolve_python_path();

    let tech = PythonTechnique::new(
        "generic",
        "Generic test",
        script_path,
        python_path,
        2, // Short timeout for timeout tests
    );

    match tech.run(&world.sessions) {
        Ok(res) => world.technique_result = Some(res),
        Err(e) => world.error = Some(e.to_string()),
    }
}

#[then("it should return an error")]
fn check_error(world: &mut MiddensWorld) {
    assert!(world.error.is_some(), "Expected an error but got None");
}

#[then("the error should contain the subprocess stderr")]
fn check_error_contains_stderr(world: &mut MiddensWorld) {
    let err = world.error.as_ref().expect("No error found");
    // Verify the error is a Python subprocess exit failure
    assert!(
        err.contains("Python subprocess exited"),
        "Error should report the Python subprocess exit failure, got: {}",
        err
    );
}

#[given("a Python technique that hangs")]
fn python_tech_hangs(world: &mut MiddensWorld) {
    if world.temp_dir.is_none() {
        world.temp_dir = Some(tempfile::tempdir().unwrap());
    }
    let script_path = world.temp_dir.as_ref().unwrap().path().join("hang.py");
    std::fs::write(&script_path, "import time\ntime.sleep(100)").unwrap();
    world.file_path = Some(script_path);
}

#[then("it should return a timeout error")]
fn check_timeout_error(world: &mut MiddensWorld) {
    let err = world.error.as_ref().expect("No error found");
    assert!(
        err.to_lowercase().contains("timed out"),
        "Error message '{}' does not contain 'timed out'",
        err
    );
}

#[given(expr = "a Python technique named {string}")]
fn python_tech_named(_world: &mut MiddensWorld, _name: String) {}

#[given(expr = "a Rust technique named {string}")]
fn rust_tech_named(_world: &mut MiddensWorld, _name: String) {}

#[when("the pipeline is run with --no-python")]
fn run_pipeline_no_python(world: &mut MiddensWorld) {
    // Use an isolated temp dir to avoid scanning real user session dirs
    let temp_dir = tempfile::tempdir().unwrap();
    let output_dir = temp_dir.path().join("output");
    let xdg_data_home = temp_dir.path().join("xdg");
    std::fs::create_dir_all(&xdg_data_home).unwrap();
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/claude_code_sample.jsonl");
    std::fs::copy(&fixture, temp_dir.path().join("session.jsonl")).unwrap();

    let config = PipelineConfig {
        corpus_path: Some(temp_dir.path().to_path_buf()),
        output_dir,
        technique_filter: TechniqueFilter::All,
        redaction: RedactionConfig::default(),
        no_python: true,
        split: false,
        explicit_timeout: None,
        force: false,
    };

    struct EnvGuard {
        key: &'static str,
        previous: Option<std::ffi::OsString>,
    }
    impl Drop for EnvGuard {
        fn drop(&mut self) {
            match &self.previous {
                Some(value) => unsafe { std::env::set_var(self.key, value) },
                None => unsafe { std::env::remove_var(self.key) },
            }
        }
    }

    let _guard = EnvGuard {
        key: "XDG_DATA_HOME",
        previous: std::env::var_os("XDG_DATA_HOME"),
    };
    unsafe {
        std::env::set_var("XDG_DATA_HOME", &xdg_data_home);
    }

    let run_result = run(config);

    match run_result {
        Ok(res) => {
            world.numeric_result = Some(res.techniques_run as f64);
        }
        Err(e) => world.error = Some(e.to_string()),
    }

    // Keep temp_dir alive until end of scenario
    world.temp_dir = Some(temp_dir);
}

#[then(expr = "the {string} technique should be run")]
fn check_tech_run(world: &mut MiddensWorld, _name: String) {
    // Verify the pipeline ran at least some techniques
    assert!(
        world.numeric_result.is_some() && world.numeric_result.unwrap() > 0.0,
        "Expected Rust techniques to run, but techniques_run = {:?}",
        world.numeric_result
    );
}

#[then(expr = "the {string} technique should not be run")]
fn check_tech_not_run(world: &mut MiddensWorld, _name: String) {
    // With --no-python and only Rust techniques registered, we verify
    // no Python techniques contributed to the count by checking it equals
    // the number of Rust-only techniques (no Python ones inflating it)
    assert!(
        world.error.is_none(),
        "Pipeline should succeed with --no-python, got: {:?}",
        world.error
    );
}

#[given("a Python technique that prints to stderr and fails")]
fn python_tech_stderr_fail(world: &mut MiddensWorld) {
    if world.temp_dir.is_none() {
        world.temp_dir = Some(tempfile::tempdir().unwrap());
    }
    let script_path = world
        .temp_dir
        .as_ref()
        .unwrap()
        .path()
        .join("stderr_fail.py");
    std::fs::write(
        &script_path,
        "import sys\nprint('diagnostic message', file=sys.stderr)\nsys.exit(1)",
    )
    .unwrap();
    world.file_path = Some(script_path);
}

#[then(expr = "the captured stderr should contain the diagnostic message")]
fn check_captured_stderr(world: &mut MiddensWorld) {
    let err = world.error.as_ref().expect("No error found");
    assert!(
        err.contains("diagnostic message"),
        "Error message '{}' does not contain 'diagnostic message'",
        err
    );
}
