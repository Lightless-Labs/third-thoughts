# NLSpec: Python Bridge Infrastructure

## Why

`middens` leverages Rust for speed and safety in core analytical tasks. However, the Python ecosystem (specifically libraries like `spacy`, `nltk`, and `scikit-learn`) offers a wealth of specialized techniques for NLP and data science that would be complex and time-consuming to port.

The Python bridge provides a standardized way to execute Python-based analysis, manage dependencies via `uv`, and integrate results into the `middens` pipeline while maintaining a unified CLI interface and output format.

## What

The Python bridge infrastructure consists of:
- **`UvManager`:** A Rust component that detects the `uv` package manager and manages a virtual environment (`venv`) for analytical techniques.
- **`PythonTechnique` Wrapper:** A Rust implementation of the `Technique` trait that delegates execution to an external Python script.
- **Data Interchange:** A JSON-based interface for passing session data to Python and receiving `TechniqueResult` back.
- **Pipeline Integration:** Filtering and execution logic to ensure Python techniques respect the `--no-python` flag.

## How

### 1. `UvManager` Implementation

**Data Model:**
```rust
pub struct UvManager {
    /// Path to the uv executable.
    uv_path: PathBuf,
    /// Path to the virtual environment managed by middens.
    venv_path: PathBuf,
    /// Path to the requirements.txt file.
    requirements_path: PathBuf,
    /// Path to the venv's Python executable (platform-aware).
    python_path: PathBuf,
}
```

**Pseudocode: `init()`**
1. Check if `uv` is in system PATH (e.g., `which uv`). If not found, return `UvError::NotFound`.
2. Ensure `~/.config/middens/python/` exists.
3. If `venv_path` doesn't exist, run `uv venv <venv_path>`.
4. Run `uv pip install -r <requirements_path>` to ensure dependencies are present.
5. Store the path to the `python` executable within the venv.

### 2. `PythonTechnique` Implementation

**Data Model:**
```rust
pub struct PythonTechnique {
    pub name: String,
    pub description: String,
    pub script_path: PathBuf,
    pub timeout_seconds: u64,
    pub python_path: PathBuf,
}
```

**Pseudocode: `run(sessions: &[Session])`**
1. Create a `NamedTempFile` (using the `tempfile` crate).
2. Serialize `sessions` into the temp file as JSON.
3. Construct command: `<python_path> <script_path> <temp_file_path>` (using the venv python directly — simpler than `uv run` since we already manage the venv via `UvManager`).
4. Spawn subprocess with a `timeout` (e.g., using `wait_timeout` crate or `std::process::Child`).
5. Capture `stdout` and `stderr`.
6. **Error Handling:**
    - If timeout reached: Kill child, return `BridgeError::Timeout`.
    - If exit code != 0: Return `BridgeError::SubprocessFailed` including the `stderr` content.
    - If `stdout` is not valid `TechniqueResult` JSON: Return `BridgeError::InvalidOutput`.
7. Deserialize `stdout` into `TechniqueResult`.
8. `NamedTempFile` is automatically deleted on drop.

### 3. Python-Side Contract

Each script in `python/techniques/` must:
1. Accept one CLI argument: `path_to_json`.
2. Load the JSON (an array of `Session` objects).
3. Process data.
4. Print exactly one JSON object to `stdout` matching the `TechniqueResult` schema.
5. Log any diagnostic information to `stderr`.

**Example `echo.py`:**
```python
import sys, json

def main():
    with open(sys.argv[1], 'r') as f:
        sessions = json.load(f)
    
    # Minimal TechniqueResult
    result = {
        "name": "Echo",
        "summary": f"Received {len(sessions)} sessions.",
        "findings": [],
        "tables": [],
        "figures": []
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
```

### 4. Integration Logic
- The `Pipeline` will call `uv_manager.init()` once if any Python techniques are enabled.
- Techniques where `requires_python()` is true are filtered out if `PipelineConfig.no_python` is set.

## Done (DoD)

- [ ] `UvManager` successfully detects `uv` or returns a clear `UvNotFound` error.
- [ ] `UvManager` creates a `venv` and installs dependencies from `requirements.txt` on first run.
- [ ] `PythonTechnique` serializes sessions to a temporary file in the OS temp directory.
- [ ] `PythonTechnique` executes the Python script using the venv's python directly.
- [ ] `PythonTechnique` captures `stderr` and includes it in the error message if the script fails.
- [ ] `PythonTechnique` returns a `Timeout` error if the script exceeds its `timeout_seconds`.
- [ ] `PythonTechnique` correctly parses valid `TechniqueResult` JSON from `stdout`.
- [ ] The `echo.py` script successfully passes the bridge end-to-end.
- [ ] The `--no-python` flag correctly bypasses all Python techniques.

## Out of Scope

- Support for Python version management beyond what `uv` provides by default.
- Dynamic installation of per-technique dependencies (all must be in the central `requirements.txt`).
- Passing data via stdin (file-based interchange is easier to debug and more robust for large payloads).
- Support for interactive or long-running Python processes.

## Design Decision Rationale

- **`uv` over `pip/venv/conda`:** `uv` is significantly faster, provides a more reliable "all-in-one" command for running scripts in environments, and simplifies our Rust-side logic.
- **Subprocess over `PyO3`:** Using subprocesses keeps the Rust binary decoupled from the Python runtime. It avoids complex linking issues, simplifies distribution, and provides better isolation (a crash in a Python script won't take down the entire Rust process).
- **JSON over Parquet/Shared Memory:** JSON is sufficient for the volume of data expected (session transcripts) and is trivial to implement and debug on both sides. If performance becomes a bottleneck, Parquet can be introduced without changing the bridge architecture.
- **File-based Interchange:** Using a temporary file instead of a pipe for input avoids potential deadlock issues with large inputs and makes it easy to inspect the data sent to Python during development.
