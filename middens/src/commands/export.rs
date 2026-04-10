use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use clap::ValueEnum;

use crate::storage::discovery::{discover_latest_analysis, discover_latest_interpretation, xdg_app_root};
use crate::storage::AnalysisRun;
use crate::view::ipynb::IpynbRenderer;
use crate::view::ViewRenderer;

#[derive(Debug, Clone, ValueEnum)]
pub enum ExportFormat {
    Jupyter,
}

pub struct ExportConfig {
    pub analysis_dir: Option<PathBuf>,
    pub interpretation_dir: Option<PathBuf>,
    pub no_interpretation: bool,
    pub format: ExportFormat,
    pub output: Option<PathBuf>,
    pub force: bool,
}

pub fn run_export(config: ExportConfig) -> Result<()> {
    let analysis_path = discover_latest_analysis(config.analysis_dir.as_deref())?;
    let run = AnalysisRun::load(&analysis_path)?;

    let xdg_analysis_root = xdg_app_root().join("analysis");
    let analysis_run_slug = if analysis_path.starts_with(&xdg_analysis_root) {
        analysis_path
            .strip_prefix(&xdg_analysis_root)
            .unwrap()
            .to_string_lossy()
            .replace(std::path::MAIN_SEPARATOR, "/")
    } else {
        analysis_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown".into())
    };

    let interp_dir = if config.no_interpretation {
        None
    } else {
        discover_latest_interpretation(&analysis_run_slug, config.interpretation_dir.as_deref())?
    };

    let renderer = match &interp_dir {
        Some(dir) => IpynbRenderer::with_interpretation(dir.clone()),
        None => IpynbRenderer::new(),
    };

    let notebook = renderer.render_run(&run)?;

    let output_path = config.output.unwrap_or_else(|| {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join("report.ipynb")
    });

    if let Some(parent) = output_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("creating output directory {}", parent.display()))?;
        }
    }

    if output_path.exists() && !config.force {
        bail!(
            "output file already exists: {}. Use --force to overwrite.",
            output_path.display()
        );
    }

    std::fs::write(&output_path, &notebook)
        .with_context(|| format!("writing notebook to {}", output_path.display()))?;

    println!("{}", output_path.display());
    Ok(())
}
