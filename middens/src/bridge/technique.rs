use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;

use anyhow::{bail, Context, Result};
use tempfile::NamedTempFile;

use crate::session::Session;
use crate::techniques::{Technique, TechniqueResult};

pub struct PythonTechnique {
    pub name: String,
    pub description: String,
    pub script_path: PathBuf,
    pub timeout_seconds: u64,
    pub python_path: PathBuf,
    /// Pre-written session cache file. When set, `run()` uses this file
    /// instead of re-serializing sessions — avoids 17× serialization cost.
    shared_sessions_path: Option<PathBuf>,
}

impl PythonTechnique {
    pub fn new(
        name: &str,
        description: &str,
        script_path: PathBuf,
        python_path: PathBuf,
        timeout_seconds: u64,
    ) -> Self {
        Self {
            name: name.to_string(),
            description: description.to_string(),
            script_path,
            timeout_seconds,
            python_path,
            shared_sessions_path: None,
        }
    }
}

impl Technique for PythonTechnique {
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn requires_python(&self) -> bool {
        true
    }

    fn is_essential(&self) -> bool {
        false
    }

    fn set_session_cache(&mut self, path: &std::path::Path) {
        self.shared_sessions_path = Some(path.to_path_buf());
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        // Use shared cache if available (written once by the pipeline),
        // otherwise create a per-technique temp file (fallback for standalone use).
        let _temp_owner;
        let input_path: &std::path::Path = if let Some(ref cached) = self.shared_sessions_path {
            cached.as_path()
        } else {
            let mut temp_file = NamedTempFile::new().context("Failed to create temp file")?;
            serde_json::to_writer(&mut temp_file, sessions)
                .context("Failed to serialize sessions to temp file")?;
            temp_file.flush().context("Failed to flush temp file")?;
            _temp_owner = temp_file.into_temp_path();
            _temp_owner.as_ref()
        };

        let mut child = Command::new(&self.python_path)
            .arg(&self.script_path)
            .arg(input_path)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .context("Failed to spawn Python subprocess")?;

        let mut stdout_pipe = child.stdout.take().context("No stdout pipe")?;
        let mut stderr_pipe = child.stderr.take().context("No stderr pipe")?;

        let stdout_thread = std::thread::spawn(move || {
            let mut buf = Vec::new();
            stdout_pipe.read_to_end(&mut buf).map(|_| buf)
        });
        let stderr_thread = std::thread::spawn(move || {
            let mut buf = Vec::new();
            stderr_pipe.read_to_end(&mut buf).map(|_| buf)
        });

        let timeout = Duration::from_secs(self.timeout_seconds);
        let start = std::time::Instant::now();

        // Poll loop: check process completion before timeout to avoid
        // false timeout on scripts that finish near the deadline.
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) => {
                    if start.elapsed() >= timeout {
                        let _ = child.kill();
                        let _ = child.wait();
                        let _ = stdout_thread.join();
                        let _ = stderr_thread.join();
                        bail!(
                            "Python subprocess timed out after {}s",
                            self.timeout_seconds
                        );
                    }
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(e) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = stdout_thread.join();
                    let _ = stderr_thread.join();
                    return Err(anyhow::anyhow!(e).context("Failed to poll subprocess"));
                }
            }
        };

        let stdout_data = stdout_thread
            .join()
            .map_err(|_| anyhow::anyhow!("stdout reader thread panicked"))?
            .context("Failed to read subprocess stdout")?;
        let stderr_data = stderr_thread
            .join()
            .map_err(|_| anyhow::anyhow!("stderr reader thread panicked"))?
            .context("Failed to read subprocess stderr")?;

        if !status.success() {
            let stderr_str = String::from_utf8_lossy(&stderr_data);
            bail!(
                "Python subprocess exited with {:?}: {}",
                status.code(),
                stderr_str
            );
        }

        // Use from_slice — TechniqueResult fields have #[serde(default)] for
        // optional/omittable fields so Python scripts don't need to emit every field.
        // Trim trailing whitespace — Python's print() adds a newline that from_slice rejects.
        let trimmed = stdout_data
            .iter()
            .rposition(|b| !b.is_ascii_whitespace())
            .map(|pos| &stdout_data[..=pos])
            .unwrap_or(&stdout_data);
        let result: TechniqueResult = serde_json::from_slice(trimmed)
            .context("Invalid JSON output from Python subprocess")?;

        Ok(result)
    }
}
