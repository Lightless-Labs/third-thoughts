use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};

use super::{AnalysisManifest, AnalysisRun};

const XDG_APP_DIR: &str = "com.lightless-labs.third-thoughts";

pub fn xdg_data_home() -> PathBuf {
    if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
        PathBuf::from(xdg)
    } else {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
        PathBuf::from(home).join(".local/share")
    }
}

pub fn xdg_app_root() -> PathBuf {
    xdg_data_home().join(XDG_APP_DIR)
}

pub fn discover_latest_analysis(analysis_dir: Option<&Path>) -> Result<PathBuf> {
    if let Some(dir) = analysis_dir {
        let run = AnalysisRun::load(dir)
            .with_context(|| format!("failed to load analysis at {}", dir.display()))?;
        check_not_split(run.manifest())?;
        return Ok(dir.to_path_buf());
    }

    let root = xdg_app_root().join("analysis");
    if !root.exists() {
        bail!(
            "no analysis runs found. Run 'middens analyze' first. \
             Expected runs under {}",
            root.display()
        );
    }

    let mut entries: Vec<String> = std::fs::read_dir(&root)
        .context("failed to read analysis directory")?
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().to_str().map(String::from))
        .filter(|name| name.starts_with("run-"))
        .collect();

    entries.sort();
    entries.reverse();

    for name in &entries {
        let candidate = root.join(name);
        if candidate.join("manifest.json").exists() {
            if let Ok(run) = AnalysisRun::load(&candidate) {
                if check_not_split(run.manifest()).is_ok() {
                    return Ok(candidate);
                }
            }
        }
    }

    bail!(
        "no analysis runs found, run 'middens analyze' first. \
         Checked: {}",
        root.display()
    )
}

pub fn discover_latest_interpretation(
    analysis_run_slug: &str,
    interpretation_dir: Option<&Path>,
) -> Result<Option<PathBuf>> {
    if let Some(dir) = interpretation_dir {
        let manifest_path = dir.join("manifest.json");
        if !manifest_path.exists() {
            bail!(
                "interpretation directory does not contain a manifest.json: {}",
                dir.display()
            );
        }
        // Validate manifest is parseable JSON
        let raw = std::fs::read_to_string(&manifest_path)
            .with_context(|| format!("reading manifest at {}", manifest_path.display()))?;
        let _: serde_json::Value = serde_json::from_str(&raw)
            .with_context(|| format!("corrupt manifest.json at {}", manifest_path.display()))?;
        return Ok(Some(dir.to_path_buf()));
    }

    let interp_root = xdg_app_root()
        .join("interpretation")
        .join(analysis_run_slug);

    if !interp_root.exists() {
        return Ok(None);
    }

    let mut entries: Vec<String> = std::fs::read_dir(&interp_root)
        .context("failed to read interpretation directory")?
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().to_str().map(String::from))
        .collect();

    entries.sort();
    entries.reverse();

    for name in &entries {
        let candidate = interp_root.join(name);
        let manifest_path = candidate.join("manifest.json");
        if manifest_path.exists() {
            // Validate parseable before selecting
            if let Ok(raw) = std::fs::read_to_string(&manifest_path) {
                if serde_json::from_str::<serde_json::Value>(&raw).is_ok() {
                    return Ok(Some(candidate));
                }
            }
        }
    }

    Ok(None)
}

pub fn check_not_split(manifest: &AnalysisManifest) -> Result<()> {
    if manifest.strata.is_some() && manifest.strata.as_ref().map_or(false, |s| !s.is_empty()) {
        bail!(
            "split runs must be addressed per stratum; pass \
             --analysis-dir <run>/interactive or <run>/subagent"
        );
    }
    Ok(())
}
