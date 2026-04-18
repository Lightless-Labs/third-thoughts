//! Embedded Python assets (technique scripts + requirements.txt).
//!
//! Scripts are baked into the binary via `include_str!` so the CLI works
//! when installed independently of the source tree. At runtime they are
//! extracted to a user cache directory (idempotent — rewritten only when
//! contents differ) so the Python subprocess can read them from disk.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

/// (filename, contents) for every technique script shipped with the CLI.
pub const TECHNIQUE_SCRIPTS: &[(&str, &str)] = &[
    ("hsmm.py", include_str!("../../python/techniques/hsmm.py")),
    (
        "information_foraging.py",
        include_str!("../../python/techniques/information_foraging.py"),
    ),
    (
        "granger_causality.py",
        include_str!("../../python/techniques/granger_causality.py"),
    ),
    (
        "survival_analysis.py",
        include_str!("../../python/techniques/survival_analysis.py"),
    ),
    (
        "process_mining.py",
        include_str!("../../python/techniques/process_mining.py"),
    ),
    (
        "prefixspan_mining.py",
        include_str!("../../python/techniques/prefixspan_mining.py"),
    ),
    (
        "smith_waterman.py",
        include_str!("../../python/techniques/smith_waterman.py"),
    ),
    (
        "tpattern_detection.py",
        include_str!("../../python/techniques/tpattern_detection.py"),
    ),
    (
        "lag_sequential.py",
        include_str!("../../python/techniques/lag_sequential.py"),
    ),
    (
        "spc_control_charts.py",
        include_str!("../../python/techniques/spc_control_charts.py"),
    ),
    (
        "ncd_clustering.py",
        include_str!("../../python/techniques/ncd_clustering.py"),
    ),
    (
        "ena_analysis.py",
        include_str!("../../python/techniques/ena_analysis.py"),
    ),
    (
        "convention_epidemiology.py",
        include_str!("../../python/techniques/convention_epidemiology.py"),
    ),
    (
        "user_signal_analysis.py",
        include_str!("../../python/techniques/user_signal_analysis.py"),
    ),
    (
        "cross_project_graph.py",
        include_str!("../../python/techniques/cross_project_graph.py"),
    ),
    (
        "change_point_detection.py",
        include_str!("../../python/techniques/change_point_detection.py"),
    ),
    (
        "corpus_timeline.py",
        include_str!("../../python/techniques/corpus_timeline.py"),
    ),
];

pub const REQUIREMENTS_TXT: &str = include_str!("../../python/requirements.txt");

/// Lowercase hex SHA-256 of the embedded `requirements.txt`. Used to
/// fingerprint the Python bridge in analysis manifests so two runs can be
/// compared for reproducibility.
pub fn requirements_hash() -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(REQUIREMENTS_TXT.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Compute the directory where embedded Python assets are extracted.
///
/// On Unix-like systems, honours `$XDG_CONFIG_HOME`, then `$HOME/.config`,
/// then the system temporary directory. On Windows, honours `%LOCALAPPDATA%`,
/// then `%USERPROFILE%\AppData\Local`, then the system temporary directory.
pub fn cache_dir() -> PathBuf {
    let base = if cfg!(windows) {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("USERPROFILE")
                    .map(PathBuf::from)
                    .map(|home| home.join("AppData").join("Local"))
            })
            .unwrap_or_else(std::env::temp_dir)
    } else {
        std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("HOME")
                    .map(PathBuf::from)
                    .map(|home| home.join(".config"))
            })
            .unwrap_or_else(std::env::temp_dir)
    };
    base.join("middens").join("python-assets")
}

/// Extract embedded scripts + requirements.txt to the cache dir.
///
/// Idempotent: files are only rewritten if contents differ from what's
/// already on disk. Returns `(scripts_dir, requirements_path)`.
pub fn extract_to(cache: &Path) -> Result<(PathBuf, PathBuf)> {
    let scripts_dir = cache.join("techniques");
    std::fs::create_dir_all(&scripts_dir)
        .with_context(|| format!("Failed to create {}", scripts_dir.display()))?;

    for (name, contents) in TECHNIQUE_SCRIPTS {
        let dest = scripts_dir.join(name);
        write_if_changed(&dest, contents.as_bytes())?;
    }

    let requirements_path = cache.join("requirements.txt");
    write_if_changed(&requirements_path, REQUIREMENTS_TXT.as_bytes())?;

    Ok((scripts_dir, requirements_path))
}

fn write_if_changed(path: &Path, contents: &[u8]) -> Result<()> {
    if let Ok(existing) = std::fs::read(path) {
        if existing == contents {
            return Ok(());
        }
    }
    std::fs::write(path, contents)
        .with_context(|| format!("Failed to write {}", path.display()))?;
    Ok(())
}
