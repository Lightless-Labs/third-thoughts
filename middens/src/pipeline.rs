use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::io::Write as _;
use std::path::PathBuf;

use anyhow::{Context, Result};
use chrono::Utc;
use sha2::{Digest, Sha256};

use crate::bridge::{UvManager, embedded};
use crate::corpus::discovery::discover_sessions;
use crate::output::{OutputMetadata, render_json, render_markdown};
use crate::parser::auto_detect::parse_auto;
use crate::storage::discovery::xdg_app_root;
use crate::storage::{
    AnalysisManifest, AnalyzerFingerprint, CorpusFingerprint, ManifestWriter, ParquetWriter,
    PythonBridgeInfo, RedactionConfig, StratumRef, TableRef, TechniqueEntry,
};
use crate::techniques::{Technique, TechniqueResult, all_techniques, all_techniques_with_python};

pub struct PipelineConfig {
    pub corpus_path: Option<PathBuf>,
    pub output_dir: PathBuf,
    pub technique_filter: TechniqueFilter,
    pub redaction: RedactionConfig,
    pub no_python: bool,
    pub split: bool,
    /// Override the auto-computed Python technique timeout (seconds).
    /// Subject to floor/ceiling checks unless `force` is true.
    pub explicit_timeout: Option<u64>,
    /// Bypass floor/ceiling timeout checks. Only meaningful when combined
    /// with `explicit_timeout`.
    pub force: bool,
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
    pub storage_dir: Option<PathBuf>,
}

pub fn run(config: PipelineConfig) -> Result<PipelineResult> {
    let _redaction_env = RedactionEnvGuard::set(&config.redaction);

    // Step 1: Discover sessions
    let files = discover_sessions(config.corpus_path.as_deref())?;
    let sessions_discovered = files.len();

    // Step 2: Parse all files
    let mut all_sessions = Vec::new();
    let mut parse_errors = 0;
    let mut sessions_parsed = 0;

    for file in &files {
        match parse_auto(file) {
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

    // Fail early on an empty corpus — do NOT write any storage or update the
    // run registry. Otherwise an empty run would sort to the top and be picked
    // up as "latest" by export/interpret. See docs/solutions/.../pre-release-review.
    if all_sessions.is_empty() {
        let target = config
            .corpus_path
            .as_deref()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|| "<auto-discovered corpus>".to_string());
        anyhow::bail!(
            "no sessions parsed from {}. Discovered {} file(s), {} parse error(s). \
             Nothing written. Verify the corpus path and that it contains Claude Code, \
             Codex, or OpenClaw session logs (.jsonl).",
            target,
            sessions_discovered,
            parse_errors
        );
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

    // Resolve timeout only when Python techniques will actually run — avoids
    // spurious floor/ceiling errors on --no-python runs.
    let timeout_seconds = if needs_python {
        resolve_timeout(all_sessions.len(), config.explicit_timeout, config.force)?
    } else {
        0 // unused
    };

    let mut python_env_failed: Option<String> = None;
    let mut python_bridge: Option<PythonBridgeInfo> = None;
    let mut all_possible: Vec<Box<dyn Technique>> = if !needs_python {
        all_techniques()
    } else {
        match prepare_python_env() {
            Ok((scripts_dir, python_path, bridge_info)) => {
                python_bridge = Some(bridge_info);
                all_techniques_with_python(&scripts_dir, &python_path, timeout_seconds)
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
                            trimmed_name,
                            reason
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

    let mut techniques = selected;

    // Step 3b: Write shared session cache for Python techniques.
    // Serializes sessions to JSON once instead of 17× (once per Python technique).
    let _session_cache_owner;
    let has_python = techniques.iter().any(|t| t.requires_python());
    if has_python {
        let mut cache_file =
            tempfile::NamedTempFile::new().context("creating session cache temp file")?;
        serde_json::to_writer(&mut cache_file, &all_sessions)
            .context("serializing sessions to cache file")?;
        cache_file.flush().context("flushing session cache")?;
        _session_cache_owner = cache_file.into_temp_path();
        for technique in techniques.iter_mut() {
            technique.set_session_cache(_session_cache_owner.as_ref());
        }
    }

    // Step 4: Create output directory
    fs::create_dir_all(&config.output_dir)?;

    // Step 5: Run techniques
    let mut techniques_run = 0;
    let mut technique_errors = 0;
    let mut interactive_sessions = 0;
    let mut subagent_sessions = 0;

    let corpus_fp = compute_corpus_fingerprint(&files, sessions_parsed, config.redaction);
    let storage_dir;

    if config.split {
        use crate::session::SessionType;
        // Unknown sessions are excluded from both strata to avoid
        // contaminating either population. See CLAUDE.md compound scoping rule.
        let interactive: Vec<_> = all_sessions
            .iter()
            .filter(|s| s.session_type == SessionType::Interactive)
            .cloned()
            .collect();
        let subagent: Vec<_> = all_sessions
            .iter()
            .filter(|s| s.session_type == SessionType::Subagent)
            .cloned()
            .collect();

        interactive_sessions = interactive.len();
        subagent_sessions = subagent.len();

        let run_id = format!("run-{}", uuid7::uuid7());
        let run_dir = xdg_app_root().join("analysis").join(&run_id);
        fs::create_dir_all(&run_dir)?;

        let mut strata_refs = Vec::new();
        let populations = vec![("interactive", interactive), ("subagent", subagent)];

        for (pop_name, pop_sessions) in populations {
            let pop_dir = config.output_dir.join(pop_name);
            fs::create_dir_all(&pop_dir)?;

            let mut technique_results = Vec::new();
            for technique in &techniques {
                match run_technique(technique, &pop_sessions, &pop_dir) {
                    Ok(result) => {
                        technique_results.push(result);
                        techniques_run += 1;
                    }
                    Err(_) => technique_errors += 1,
                }
            }

            let stratum_dir = run_dir.join(pop_name);
            write_storage_layer(
                technique_results,
                &corpus_fp,
                &run_id,
                Some(pop_name),
                None,
                &stratum_dir,
                python_bridge.as_ref(),
            )?;

            strata_refs.push(StratumRef {
                name: pop_name.to_string(),
                session_count: pop_sessions.len() as i64,
                manifest_ref: format!("{}/manifest.json", pop_name),
            });
        }

        // Top-level split manifest (strata refs, no technique data)
        let top_manifest = AnalysisManifest {
            run_id: run_id.clone(),
            created_at: Utc::now(),
            analyzer_fingerprint: AnalyzerFingerprint {
                middens_version: env!("CARGO_PKG_VERSION").to_string(),
                git_sha: None,
                technique_versions: BTreeMap::new(),
                python_bridge: python_bridge.clone(),
            },
            corpus_fingerprint: corpus_fp.clone(),
            strata: Some(strata_refs),
            stratum: None,
            techniques: vec![],
        };
        ManifestWriter::write(&top_manifest, &run_dir.join("manifest.json"))?;

        storage_dir = Some(run_dir);
    } else {
        let mut technique_results = Vec::new();
        for technique in &techniques {
            match run_technique(technique, &all_sessions, &config.output_dir) {
                Ok(result) => {
                    technique_results.push(result);
                    techniques_run += 1;
                }
                Err(_) => technique_errors += 1,
            }
        }

        let run_id = format!("run-{}", uuid7::uuid7());
        let run_dir = xdg_app_root().join("analysis").join(&run_id);
        write_storage_layer(
            technique_results,
            &corpus_fp,
            &run_id,
            None,
            None,
            &run_dir,
            python_bridge.as_ref(),
        )?;

        storage_dir = Some(run_dir);
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
        storage_dir,
    })
}

fn run_technique(
    technique: &Box<dyn Technique>,
    sessions: &[crate::session::Session],
    output_dir: &std::path::Path,
) -> Result<TechniqueResult> {
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
                    technique.name(),
                    md_path.display(),
                    e
                );
                return Err(e.into());
            }

            let json_pretty = serde_json::to_string_pretty(&json_val).map_err(|e| {
                eprintln!(
                    "middens: failed to serialize JSON for '{}': {}",
                    technique.name(),
                    e
                );
                anyhow::anyhow!(e).context(format!("serializing {} JSON", technique.name()))
            })?;

            fs::write(&json_path, json_pretty).map_err(|e| {
                eprintln!(
                    "middens: failed to write JSON for '{}' to {}: {}",
                    technique.name(),
                    json_path.display(),
                    e
                );
                anyhow::anyhow!(e).context(format!("writing {}", json_path.display()))
            })?;

            Ok(result)
        }
        Err(e) => {
            eprintln!("middens: technique '{}' failed: {}", technique.name(), e);
            Err(e)
        }
    }
}

fn compute_corpus_fingerprint(
    files: &[PathBuf],
    session_count: usize,
    redaction: RedactionConfig,
) -> CorpusFingerprint {
    let mut full_path_strings: Vec<String> = files
        .iter()
        .map(|p| p.to_string_lossy().to_string())
        .collect();
    full_path_strings.sort();

    let mut hasher = Sha256::new();
    for p in &full_path_strings {
        hasher.update(p.as_bytes());
        hasher.update(b"\n");
    }
    let manifest_hash = format!("{:x}", hasher.finalize());
    let short = manifest_hash[..8].to_string();

    let mut source_paths: Vec<String> = files
        .iter()
        .map(|path| redaction.display_source_path(path))
        .collect();
    source_paths.sort();

    CorpusFingerprint {
        manifest_hash,
        short,
        session_count: session_count as i64,
        source_paths,
    }
}

struct EnvVarGuard {
    key: &'static str,
    previous: Option<OsString>,
}

impl EnvVarGuard {
    fn set(key: &'static str, value: &str) -> Self {
        let previous = std::env::var_os(key);
        unsafe {
            std::env::set_var(key, value);
        }
        Self { key, previous }
    }
}

impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        unsafe {
            match &self.previous {
                Some(value) => std::env::set_var(self.key, value),
                None => std::env::remove_var(self.key),
            }
        }
    }
}

struct RedactionEnvGuard {
    _source_paths: EnvVarGuard,
    _project_names: EnvVarGuard,
}

impl RedactionEnvGuard {
    fn set(redaction: &RedactionConfig) -> Self {
        Self {
            _source_paths: EnvVarGuard::set(
                "MIDDENS_INCLUDE_SOURCE_PATHS",
                if redaction.include_source_paths {
                    "1"
                } else {
                    "0"
                },
            ),
            _project_names: EnvVarGuard::set(
                "MIDDENS_INCLUDE_PROJECT_NAMES",
                if redaction.include_project_names {
                    "1"
                } else {
                    "0"
                },
            ),
        }
    }
}

const TIMEOUT_FLOOR: u64 = 60;
const TIMEOUT_CEILING: u64 = 1800;

/// Auto-computes a per-run timeout from corpus size: 100 × ln(n), clamped to
/// [TIMEOUT_FLOOR, TIMEOUT_CEILING]. Scales from ~60s (tiny corpora) up to
/// ~951s at 13k sessions — always within bounds, no --force needed.
fn compute_timeout_secs(session_count: usize) -> u64 {
    let raw = 100.0_f64 * (session_count.max(1) as f64).ln();
    (raw as u64).clamp(TIMEOUT_FLOOR, TIMEOUT_CEILING)
}

/// Resolves the final timeout to use.
/// - Auto (no explicit value): clamp silently within [floor, ceiling].
/// - Explicit value: reject outside [floor, ceiling] unless force=true.
fn resolve_timeout(
    session_count: usize,
    explicit: Option<u64>,
    force: bool,
) -> anyhow::Result<u64> {
    match explicit {
        None => Ok(compute_timeout_secs(session_count)),
        Some(t) if force => Ok(t),
        Some(t) if t < TIMEOUT_FLOOR => anyhow::bail!(
            "explicit --timeout {}s is below the {}s floor to guard against accidental \
             short-circuits; pass --force to override",
            t,
            TIMEOUT_FLOOR
        ),
        Some(t) if t > TIMEOUT_CEILING => anyhow::bail!(
            "explicit --timeout {}s exceeds the {}s ceiling; pass --force to run anyway",
            t,
            TIMEOUT_CEILING
        ),
        Some(t) => Ok(t),
    }
}

fn write_storage_layer(
    results: Vec<TechniqueResult>,
    corpus_fp: &CorpusFingerprint,
    run_id: &str,
    stratum: Option<&str>,
    strata: Option<Vec<StratumRef>>,
    run_dir: &std::path::Path,
    python_bridge: Option<&PythonBridgeInfo>,
) -> Result<()> {
    fs::create_dir_all(run_dir)?;
    let data_dir = run_dir.join("data");
    fs::create_dir_all(&data_dir)?;

    let mut technique_entries = Vec::new();
    let mut technique_versions = BTreeMap::new();

    for result in results {
        let TechniqueResult {
            name,
            summary,
            findings,
            tables,
            figures,
        } = result;

        let table_ref = if let Some(table) = tables.into_iter().next() {
            let parquet_rel = format!("data/{}.parquet", name);
            let parquet_path = run_dir.join(&parquet_rel);
            ParquetWriter::write_table(&table, &name, &parquet_path)
                .with_context(|| format!("writing parquet for technique '{}'", name))?;
            Some(TableRef {
                name: table.name.clone(),
                parquet: parquet_rel,
                row_count: table.rows.len() as i64,
                column_types: table.column_types.clone(),
            })
        } else {
            None
        };

        let version = env!("CARGO_PKG_VERSION").to_string();
        technique_versions.insert(name.clone(), version.clone());

        technique_entries.push(TechniqueEntry {
            name,
            version,
            summary,
            findings,
            table: table_ref,
            figures,
            errors: vec![],
        });
    }

    let manifest = AnalysisManifest {
        run_id: run_id.to_string(),
        created_at: Utc::now(),
        analyzer_fingerprint: AnalyzerFingerprint {
            middens_version: env!("CARGO_PKG_VERSION").to_string(),
            git_sha: None,
            technique_versions,
            python_bridge: python_bridge.cloned(),
        },
        corpus_fingerprint: corpus_fp.clone(),
        strata,
        stratum: stratum.map(String::from),
        techniques: technique_entries,
    };

    ManifestWriter::write(&manifest, &run_dir.join("manifest.json"))
}

/// Extract embedded Python assets, detect `uv`, and initialise the shared
/// middens venv. Returns `(scripts_dir, python_path, bridge_info)` on
/// success — the bridge info is recorded in analysis manifests so two runs
/// can be compared for Python-stack reproducibility.
fn prepare_python_env() -> Result<(PathBuf, PathBuf, PythonBridgeInfo)> {
    let cache = embedded::cache_dir();
    std::fs::create_dir_all(&cache)?;
    let (scripts_dir, requirements_path) = embedded::extract_to(&cache)?;
    let uv = UvManager::detect(requirements_path)?;
    uv.init()?;
    let bridge_info = PythonBridgeInfo {
        uv_version: uv.uv_version(),
        requirements_hash: embedded::requirements_hash(),
    };
    Ok((scripts_dir, uv.python_path().clone(), bridge_info))
}

#[cfg(test)]
mod tests {
    use super::compute_corpus_fingerprint;
    use crate::storage::RedactionConfig;
    use sha2::{Digest, Sha256};
    use std::path::PathBuf;

    #[test]
    fn corpus_fingerprint_scrubs_paths_by_default() {
        let files = vec![
            PathBuf::from("/Users/alice/projects/alpha/session-a.jsonl"),
            PathBuf::from("/Users/alice/projects/beta/session-b.jsonl"),
        ];

        let scrubbed = compute_corpus_fingerprint(&files, 2, RedactionConfig::default());
        assert_eq!(
            scrubbed.source_paths,
            vec!["session-a.jsonl".to_string(), "session-b.jsonl".to_string()]
        );

        let raw = compute_corpus_fingerprint(
            &files,
            2,
            RedactionConfig {
                include_source_paths: true,
                include_project_names: false,
            },
        );
        assert_eq!(
            raw.source_paths,
            vec![
                "/Users/alice/projects/alpha/session-a.jsonl".to_string(),
                "/Users/alice/projects/beta/session-b.jsonl".to_string(),
            ]
        );

        let mut hasher = Sha256::new();
        for path in [
            "/Users/alice/projects/alpha/session-a.jsonl",
            "/Users/alice/projects/beta/session-b.jsonl",
        ] {
            hasher.update(path.as_bytes());
            hasher.update(b"\n");
        }
        let expected_hash = format!("{:x}", hasher.finalize());

        assert_eq!(scrubbed.manifest_hash, expected_hash);
        assert_eq!(raw.manifest_hash, expected_hash);
    }
}
