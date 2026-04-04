use std::path::PathBuf;
use std::process::Command;

use anyhow::{bail, Context, Result};

pub struct UvManager {
    uv_path: PathBuf,
    venv_path: PathBuf,
    requirements_path: PathBuf,
    python_path: PathBuf,
}

impl UvManager {
    fn config_base() -> PathBuf {
        std::env::var("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                let home = std::env::var("HOME")
                    .or_else(|_| std::env::var("USERPROFILE"))
                    .unwrap_or_else(|_| "/tmp".to_string());
                PathBuf::from(home).join(".config")
            })
    }

    fn venv_python_path(venv_path: &PathBuf) -> PathBuf {
        if cfg!(windows) {
            venv_path.join("Scripts").join("python.exe")
        } else {
            venv_path.join("bin").join("python")
        }
    }

    pub fn detect(requirements_path: PathBuf) -> Result<Self> {
        let uv_path = which::which("uv").context("uv not found in PATH")?;
        let config_base = Self::config_base();
        let venv_path = config_base.join("middens").join("python");
        let python_path = Self::venv_python_path(&venv_path);
        Ok(Self {
            uv_path,
            venv_path,
            requirements_path,
            python_path,
        })
    }

    pub fn init(&self) -> Result<()> {
        std::fs::create_dir_all(&self.venv_path).context("Failed to create venv directory")?;

        if !self.python_path.exists() {
            let output = Command::new(&self.uv_path)
                .arg("venv")
                .arg(&self.venv_path)
                .output()
                .context("Failed to run uv venv")?;
            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                bail!("uv venv failed: {}", stderr);
            }
        }

        if self.requirements_path.exists() {
            let output = Command::new(&self.uv_path)
                .args(["pip", "install", "--python"])
                .arg(&self.python_path)
                .arg("-r")
                .arg(&self.requirements_path)
                .output()
                .context("Failed to run uv pip install")?;
            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                bail!("uv pip install failed: {}", stderr);
            }
        }

        Ok(())
    }

    pub fn python_path(&self) -> &PathBuf {
        &self.python_path
    }

    pub fn venv_path(&self) -> &PathBuf {
        &self.venv_path
    }

    pub fn uv_path(&self) -> &PathBuf {
        &self.uv_path
    }
}
