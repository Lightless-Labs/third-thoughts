use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use anyhow::Result;
use chrono::Utc;

use crate::bridge::{UvManager, embedded};
use crate::corpus::discovery::discover_sessions;
use crate::output::{OutputMetadata, render_json, render_markdown};
use crate::parser::auto_detect::parse_auto;
use crate::techniques::{Technique, all_techniques, all_techniques_with_python};

pub struct PipelineConfig {
    pub corpus_path: Option<PathBuf>,
    pub output_dir: PathBuf,
    pub technique_filter: TechniqueFilter,
    pub no_python: bool,
    pub split: bool,
}

pub enum TechniqueFilter {
    Essential,
    All,
    Named(Vec<String>),
}

pub struct PipelineResult {
    pub sessions_discovered: usize,
    pub sessions_parsed: usize,
    pub interactive_sessions: usize,
    pub subagent_sessions: usize,
    pub parse_errors: usize,
    pub techniques_run: usize,
    pub technique_errors: usize,
    pub output_dir: PathBuf,
}

pub fn run(config: PipelineConfig) -> Result<PipelineResult> {
    // Step 1: Discover sessions
    let files = discover_sessions(config.corpus_path.as_deref())?;
    let sessions_discovered = files.len();

    // Step 2: Parse all files
    let mut all_sessions = Vec::new();
    let mut parse_errors = 0;
    let mut sessions_parsed = 0;

    for file in files {
        match parse_auto(&file) {
            Ok(sessions) => {
                sessions_parsed += sessions.len();
                all_sessions.extend(sessions);
            }
            Err(e) => {
                eprintln!("middens: failed to parse {}: {}", file.display(), e);
                parse_errors += 1;
            }
        }
    }

    // Step 3: Select techniques — include Python-bridged ones only when the
    // current filter actually selects at least one of them. This avoids
    // paying `uv` detection / extraction cost on runs that only use Rust
    // techniques (e.g. `--essential`). Failures degrade gracefully to
    // Rust-only techniques (with a stderr warning) so the CLI is still
    // usable on systems without `uv` installed.
    let python_technique_names: std::collections::HashSet<&str> =
        crate::techniques::PYTHON_TECHNIQUE_MANIFEST
            .iter()
            .map(|(n, _, _)| *n)
            .collect();

    let needs_python = !config.no_python
        && match &config.technique_filter {
            TechniqueFilter::All => true,
            TechniqueFilter::Essential => false,
            TechniqueFilter::Named(names) => names
                .iter()
                .any(|n| python_technique_names.contains(n.trim())),
        };

    let mut python_env_failed: Option<String> = None;
    let mut all_possible: Vec<Box<dyn Technique>> = if !needs_python {
        all_techniques()
    } else {
        match prepare_python_env() {
            Ok((scripts_dir, python_path)) => {
                all_techniques_with_python(&scripts_dir, &python_path, 300)
            }
            Err(e) => {
                eprintln!(
                    "middens: warning: Python techniques unavailable ({}). \
                     Running Rust-only. Pass --no-python to silence.",
                    e
                );
                python_env_failed = Some(e.to_string());
                all_techniques()
            }
        }
    };
    let mut selected: Vec<Box<dyn Technique>> = match config.technique_filter {
        TechniqueFilter::All => all_possible,
        TechniqueFilter::Essential => all_possible
            .into_iter()
            .filter(|t| t.is_essential())
            .collect(),
        TechniqueFilter::Named(names) => {
            let mut filtered = Vec::new();
            for name in names {
                let trimmed_name = name.trim();
                if let Some(pos) = all_possible.iter().position(|t| t.name() == trimmed_name) {
                    filtered.push(all_possible.remove(pos));
                } else if let Some(reason) = &python_env_failed {
                    if python_technique_names.contains(trimmed_name) {
                        // Explicitly requested by name AND would have been
                        // available if Python had loaded — fail loud rather
                        // than silently dropping the request.
                        anyhow::bail!(
                            "middens: technique '{}' requires Python but the Python \
                             environment failed to prepare ({}). Install `uv` (https://docs.astral.sh/uv/) \
                             or pass --no-python to skip Python techniques entirely.",
                            trimmed_name, reason
                        );
                    } else {
                        eprintln!("middens: warning: unknown technique '{}'", trimmed_name);
                    }
                } else {
                    eprintln!("middens: warning: unknown technique '{}'", trimmed_name);
                }
            }
            filtered
        }
    };

    // Filter by python requirement
    if config.no_python {
        selected.retain(|t| !t.requires_python());
    }

    let techniques = selected;

    // Step 4: Create output directory
    fs::create_dir_all(&config.output_dir)?;

    // Step 5: Run techniques
    let mut techniques_run = 0;
    let mut technique_errors = 0;
    let mut interactive_sessions = 0;
    let mut subagent_sessions = 0;

    if config.split {
        use crate::session::SessionType;
        let interactive: Vec<_> = all_sessions
            .iter()
            .filter(|s| s.session_type == SessionType::Interactive || s.session_type == SessionType::Unknown)
            .cloned()
            .collect();
        let subagent: Vec<_> = all_sessions
            .iter()
            .filter(|s| s.session_type == SessionType::Subagent || s.session_type == SessionType::Unknown)
            .cloned()
            .collect();

        interactive_sessions = interactive.len();
        subagent_sessions = subagent.len();

        let populations = vec![
            ("interactive", interactive),
            ("subagent", subagent),
        ];

        for (pop_name, pop_sessions) in populations {
            let pop_dir = config.output_dir.join(pop_name);
            fs::create_dir_all(&pop_dir)?;

            for technique in &techniques {
                match run_technique(technique, &pop_sessions, &pop_dir) {
                    Ok(_) => techniques_run += 1,
                    Err(_) => technique_errors += 1,
                }
            }
        }
    } else {
        for technique in &techniques {
            match run_technique(technique, &all_sessions, &config.output_dir) {
                Ok(_) => techniques_run += 1,
                Err(_) => technique_errors += 1,
            }
        }
    }

    // Step 6: Return result
    Ok(PipelineResult {
        sessions_discovered,
        sessions_parsed,
        interactive_sessions,
        subagent_sessions,
        parse_errors,
        techniques_run,
        technique_errors,
        output_dir: config.output_dir,
    })
}

fn run_technique(technique: &Box<dyn Technique>, sessions: &[crate::session::Session], output_dir: &std::path::Path) -> Result<()> {
    match technique.run(sessions) {
        Ok(result) => {
            let meta = OutputMetadata {
                technique_name: technique.name().to_string(),
                corpus_size: sessions.len() as u64,
                generated_at: Utc::now().to_rfc3339(),
                middens_version: env!("CARGO_PKG_VERSION").to_string(),
                parameters: BTreeMap::new(),
            };

            let md = render_markdown(&result, &meta);
            let json_val = render_json(&result, &meta);
            let md_path = output_dir.join(format!("{}.md", technique.name()));
            let json_path = output_dir.join(format!("{}.json", technique.name()));

            if let Err(e) = fs::write(&md_path, md) {
                eprintln!(
                    "middens: failed to write markdown for '{}' to {}: {}",
                    technique.name(), md_path.display(), e
                );
                return Err(e.into());
            }

            let json_pretty = serde_json::to_string_pretty(&json_val)
                .map_err(|e| {
                    eprintln!("middens: failed to serialize JSON for '{}': {}", technique.name(), e);
                    anyhow::anyhow!(e).context(format!("serializing {} JSON", technique.name()))
                })?;

            fs::write(&json_path, json_pretty).map_err(|e| {
                eprintln!(
                    "middens: failed to write JSON for '{}' to {}: {}",
                    technique.name(), json_path.display(), e
                );
                anyhow::anyhow!(e).context(format!("writing {}", json_path.display()))
            })?;

            Ok(())
        }
        Err(e) => {
            eprintln!("middens: technique '{}' failed: {}", technique.name(), e);
            Err(e)
        }
    }
}

/// Extract embedded Python assets, detect `uv`, and initialise the shared
/// middens venv. Returns `(scripts_dir, python_path)` on success.
fn prepare_python_env() -> Result<(PathBuf, PathBuf)> {
    let cache = embedded::cache_dir();
    std::fs::create_dir_all(&cache)?;
    let (scripts_dir, requirements_path) = embedded::extract_to(&cache)?;
    let uv = UvManager::detect(requirements_path)?;
    uv.init()?;
    Ok((scripts_dir, uv.python_path().clone()))
}
